"""
Circuit Breaker para proteção contra falhas em cascata.
Evita banimento por insistência em portais com problemas.
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"  # Normal, permitindo requisições
    OPEN = "open"  # Bloqueado, rejeitando requisições
    HALF_OPEN = "half_open"  # Testando se pode voltar ao normal


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5  # Falhas consecutivas para abrir
    success_threshold: int = 2  # Sucessos para fechar (em half-open)
    timeout_seconds: int = 60  # Tempo em open antes de half-open
    excluded_exceptions: tuple = ()  # Exceções que não contam como falha


@dataclass
class CircuitStats:
    failures: int = 0
    successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    total_calls: int = 0
    total_failures: int = 0


class CircuitBreaker:
    """
    Circuit Breaker por portal.
    Protege contra falhas em cascata e evita banimento por insistência.
    """
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitStats()
        self._state_changed_at = time.time()
        self._lock = asyncio.Lock()
    
    @property
    def is_available(self) -> bool:
        """Verifica se o circuit breaker permite requisições."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.time() - self._state_changed_at >= self.config.timeout_seconds:
                return True  # Pode tentar half-open
            return False
        return True  # half-open permite uma tentativa
    
    async def call(self, func: Callable, *args, **kwargs):
        """Executa função protegida pelo circuit breaker."""
        async with self._lock:
            if not self.is_available:
                raise CircuitOpenError(
                    f"Circuit breaker '{self.name}' está aberto. "
                    f"Aguarde {self.config.timeout_seconds}s."
                )
            
            if self.state == CircuitState.OPEN:
                self._transition_to(CircuitState.HALF_OPEN)
        
        try:
            result = await func(*args, **kwargs)
            await self._record_success()
            return result
        except self.config.excluded_exceptions:
            raise
        except Exception as e:
            await self._record_failure(e)
            raise
    
    async def _record_success(self):
        """Registra sucesso."""
        async with self._lock:
            self.stats.successes += 1
            self.stats.last_success_time = time.time()
            self.stats.total_calls += 1
            
            if self.state == CircuitState.HALF_OPEN:
                if self.stats.successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            else:
                self.stats.failures = 0
    
    async def _record_failure(self, error: Exception):
        """Registra falha."""
        async with self._lock:
            self.stats.failures += 1
            self.stats.total_failures += 1
            self.stats.last_failure_time = time.time()
            self.stats.total_calls += 1
            
            logger.warning(
                "Circuit breaker '%s': falha %d/%d - %s",
                self.name, self.stats.failures, self.config.failure_threshold, error
            )
            
            if self.state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self.stats.failures >= self.config.failure_threshold:
                self._transition_to(CircuitState.OPEN)
    
    def _transition_to(self, new_state: CircuitState):
        """Transição de estado."""
        old_state = self.state
        self.state = new_state
        self._state_changed_at = time.time()
        
        if new_state == CircuitState.CLOSED:
            self.stats.failures = 0
            self.stats.successes = 0
        
        logger.info(
            "Circuit breaker '%s': %s -> %s",
            self.name, old_state.value, new_state.value
        )
    
    def get_status(self) -> dict:
        """Retorna status atual."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failures": self.stats.failures,
            "successes": self.stats.successes,
            "total_calls": self.stats.total_calls,
            "total_failures": self.stats.total_failures,
            "time_in_state": time.time() - self._state_changed_at,
        }


class CircuitOpenError(Exception):
    """Exceção quando circuit breaker está aberto."""
    pass


class CircuitBreakerRegistry:
    """Registro global de circuit breakers por portal."""
    
    _breakers: dict[str, CircuitBreaker] = {}
    
    @classmethod
    def get(cls, portal_name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Obtém ou cria circuit breaker para um portal."""
        if portal_name not in cls._breakers:
            cls._breakers[portal_name] = CircuitBreaker(portal_name, config)
        return cls._breakers[portal_name]
    
    @classmethod
    def get_all_status(cls) -> list[dict]:
        """Retorna status de todos os circuit breakers."""
        return [cb.get_status() for cb in cls._breakers.values()]
    
    @classmethod
    def reset(cls, portal_name: str):
        """Reset manual de um circuit breaker."""
        if portal_name in cls._breakers:
            cls._breakers[portal_name]._transition_to(CircuitState.CLOSED)
