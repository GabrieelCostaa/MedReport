"""
Mecanismo de retry com backoff exponencial.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional, Type
import random

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """Configuração de retry."""
    max_attempts: int = 3
    backoff_seconds: list[int] | None = None
    jitter: bool = True  # Adiciona variação aleatória
    retry_exceptions: tuple[Type[Exception], ...] = (Exception,)
    on_retry: Optional[Callable] = None  # Callback em cada retry


class RetryExhaustedError(Exception):
    """Todas as tentativas falharam."""
    def __init__(self, message: str, last_error: Exception, attempts: int):
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts


async def retry_async(
    func: Callable,
    config: Optional[RetryConfig] = None,
    *args,
    **kwargs
):
    """
    Executa função com retry e backoff.
    
    Args:
        func: Função assíncrona a executar
        config: Configuração de retry
        *args, **kwargs: Argumentos para a função
    
    Returns:
        Resultado da função
    
    Raises:
        RetryExhaustedError: Se todas as tentativas falharem
    """
    config = config or RetryConfig()
    backoff = config.backoff_seconds or [10, 60, 300]
    
    last_error = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await func(*args, **kwargs)
        except config.retry_exceptions as e:
            last_error = e
            
            if attempt >= config.max_attempts:
                break
            
            wait_index = min(attempt - 1, len(backoff) - 1)
            wait_time = backoff[wait_index]
            
            if config.jitter:
                wait_time = wait_time * (0.5 + random.random())
            
            logger.warning(
                "Tentativa %d/%d falhou: %s. Aguardando %.1fs...",
                attempt, config.max_attempts, e, wait_time
            )
            
            if config.on_retry:
                try:
                    await config.on_retry(attempt, e, wait_time)
                except Exception:
                    pass
            
            await asyncio.sleep(wait_time)
    
    raise RetryExhaustedError(
        f"Todas as {config.max_attempts} tentativas falharam",
        last_error,
        config.max_attempts
    )


def with_retry(config: Optional[RetryConfig] = None):
    """
    Decorator para adicionar retry a funções assíncronas.
    
    Exemplo:
        @with_retry(RetryConfig(max_attempts=3))
        async def fetch_data():
            ...
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            return await retry_async(func, config, *args, **kwargs)
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager para retry com estado.
    
    Exemplo:
        async with RetryContext(config) as ctx:
            while ctx.should_retry:
                try:
                    result = await do_something()
                    ctx.success()
                    break
                except Exception as e:
                    await ctx.failed(e)
    """
    
    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
        self.attempt = 0
        self.last_error: Optional[Exception] = None
        self._succeeded = False
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
    
    @property
    def should_retry(self) -> bool:
        """Verifica se deve continuar tentando."""
        return not self._succeeded and self.attempt < self.config.max_attempts
    
    def success(self):
        """Marca como sucesso."""
        self._succeeded = True
    
    async def failed(self, error: Exception):
        """Registra falha e aguarda backoff."""
        self.last_error = error
        self.attempt += 1
        
        if self.attempt >= self.config.max_attempts:
            raise RetryExhaustedError(
                f"Todas as {self.config.max_attempts} tentativas falharam",
                error,
                self.attempt
            )
        
        backoff = self.config.backoff_seconds or [10, 60, 300]
        wait_index = min(self.attempt - 1, len(backoff) - 1)
        wait_time = backoff[wait_index]
        
        if self.config.jitter:
            wait_time = wait_time * (0.5 + random.random())
        
        logger.warning(
            "Tentativa %d/%d falhou: %s. Aguardando %.1fs...",
            self.attempt, self.config.max_attempts, error, wait_time
        )
        
        await asyncio.sleep(wait_time)
