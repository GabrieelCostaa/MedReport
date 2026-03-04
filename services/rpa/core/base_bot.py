"""
Classe base para bots RPA.
Define interface comum e funcionalidades compartilhadas.
"""
import asyncio
import hashlib
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    from core.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
    from core.config import PortalConfig, RpaConfig, DEFAULT_CONFIG
    from core.metrics import GLOBAL_METRICS, RunMetrics, Timer
    from core.retry import RetryConfig, retry_async
except ImportError:
    from .circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
    from .config import PortalConfig, RpaConfig, DEFAULT_CONFIG
    from .metrics import GLOBAL_METRICS, RunMetrics, Timer
    from .retry import RetryConfig, retry_async

logger = logging.getLogger(__name__)


@dataclass
class CapturedQuote:
    """Cotação capturada pelo bot."""
    external_id: str
    portal: str
    status: str = "open"
    published_at: Optional[str] = None
    deadline_at: Optional[str] = None
    buyer_name: Optional[str] = None
    buyer_type: Optional[str] = None
    delivery_city: Optional[str] = None
    delivery_state: Optional[str] = None
    items: list[dict] = field(default_factory=list)
    attachments: list[dict] = field(default_factory=list)
    raw_html: Optional[str] = None
    raw_payload: Optional[dict] = None


@dataclass
class JobConfig:
    """Configuração de um job de coleta."""
    tenant_id: str
    portal: str
    mode: str = "poll"  # poll | full_sync
    filters: dict = field(default_factory=dict)
    max_quotations: int = 50
    max_items_per_quotation: int = 500
    download_attachments: bool = True
    timeout_seconds: int = 900
    credentials_secret_id: Optional[str] = None


class BaseBot(ABC):
    """
    Classe base para implementação de bots RPA.
    
    Cada portal deve ter uma classe que herda de BaseBot
    e implementa os métodos abstratos.
    """
    
    def __init__(
        self,
        portal_config: PortalConfig,
        rpa_config: Optional[RpaConfig] = None,
    ):
        self.portal_config = portal_config
        self.rpa_config = rpa_config or DEFAULT_CONFIG
        self.run_id = str(uuid.uuid4())
        self.metrics: Optional[RunMetrics] = None
        self._browser = None
        self._context = None
        self._page = None
    
    @property
    def portal_name(self) -> str:
        return self.portal_config.name
    
    async def execute(self, job: JobConfig) -> list[CapturedQuote]:
        """
        Executa job de coleta completo.
        Orquestra login, navegação, captura e cleanup.
        """
        circuit_breaker = CircuitBreakerRegistry.get(self.portal_name)
        
        self.metrics = GLOBAL_METRICS.start_run(
            self.run_id, self.portal_name, job.tenant_id
        )
        
        quotes: list[CapturedQuote] = []
        
        try:
            async def _run():
                nonlocal quotes
                await self._setup_browser()
                
                with Timer("login") as t:
                    await self._do_login(job)
                self.metrics.login_duration_ms = t.elapsed_ms
                
                with Timer("navigation") as t:
                    await self._navigate_to_quotes(job)
                self.metrics.navigation_duration_ms = t.elapsed_ms
                
                with Timer("capture") as t:
                    quotes = await self._capture_quotes(job)
                self.metrics.capture_duration_ms = t.elapsed_ms
                
                self.metrics.quotes_found = len(quotes)
                self.metrics.items_captured = sum(len(q.items) for q in quotes)
                self.metrics.attachments_downloaded = sum(
                    len([a for a in q.attachments if a.get("downloaded")])
                    for q in quotes
                )
                
                return quotes
            
            quotes = await circuit_breaker.call(_run)
            GLOBAL_METRICS.finish_run(self.run_id, "success")
            
        except CircuitOpenError as e:
            logger.error("Circuit breaker aberto para %s: %s", self.portal_name, e)
            self.metrics.errors.append(str(e))
            GLOBAL_METRICS.finish_run(self.run_id, "circuit_open")
            raise
        except Exception as e:
            logger.exception("Erro na execução do bot %s: %s", self.portal_name, e)
            self.metrics.errors.append(str(e))
            GLOBAL_METRICS.finish_run(self.run_id, "failed")
            raise
        finally:
            await self._cleanup()
        
        return quotes
    
    async def _setup_browser(self):
        """Inicializa browser headless."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError("Playwright não instalado. Execute: pip install playwright && playwright install")
        
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.rpa_config.headless
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(self.portal_config.timeout_seconds * 1000)
    
    async def _cleanup(self):
        """Limpa recursos do browser."""
        try:
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if hasattr(self, '_playwright') and self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning("Erro no cleanup: %s", e)
    
    async def _do_login(self, job: JobConfig):
        """Executa login com retry."""
        retry_config = RetryConfig(
            max_attempts=self.portal_config.retry_policy.max_attempts,
            backoff_seconds=self.portal_config.retry_policy.backoff_seconds,
        )
        
        try:
            await retry_async(self.login, retry_config, job)
        except Exception as e:
            self.metrics.login_failed = True
            raise
    
    async def _navigate_to_quotes(self, job: JobConfig):
        """Navega até listagem de cotações."""
        await self.navigate_to_list(job)
        self.metrics.pages_visited += 1
    
    async def _capture_quotes(self, job: JobConfig) -> list[CapturedQuote]:
        """Captura cotações da listagem."""
        quotes = []
        quote_refs = await self.get_quote_list(job)
        
        for i, ref in enumerate(quote_refs[:job.max_quotations]):
            try:
                quote = await self.capture_quote_detail(ref, job)
                if quote:
                    quotes.append(quote)
                    self.metrics.pages_visited += 1
                    
                    if job.download_attachments and quote.attachments:
                        await self._download_attachments(quote)
            except Exception as e:
                logger.warning("Erro ao capturar cotação %s: %s", ref, e)
                self.metrics.errors.append(f"Quote {ref}: {e}")
        
        return quotes
    
    async def _download_attachments(self, quote: CapturedQuote):
        """Baixa anexos de uma cotação."""
        storage_path = Path(self.rpa_config.storage_path) / self.portal_name / quote.external_id
        storage_path.mkdir(parents=True, exist_ok=True)
        
        for attachment in quote.attachments:
            if attachment.get("downloaded"):
                continue
            
            try:
                url = attachment.get("url")
                if not url:
                    continue
                
                filename = attachment.get("filename", f"attachment_{uuid.uuid4().hex[:8]}")
                filepath = storage_path / filename
                
                download = await self._page.wait_for_download(
                    lambda: self._page.goto(url)
                )
                await download.save_as(str(filepath))
                
                with open(filepath, "rb") as f:
                    sha256 = hashlib.sha256(f.read()).hexdigest()
                
                attachment["downloaded"] = True
                attachment["storage_uri"] = str(filepath)
                attachment["sha256"] = sha256
                attachment["size_bytes"] = filepath.stat().st_size
                
                self.metrics.attachments_downloaded += 1
                
            except Exception as e:
                logger.warning("Erro ao baixar anexo %s: %s", attachment.get("filename"), e)
                attachment["error"] = str(e)
    
    async def take_screenshot(self, name: str) -> Optional[str]:
        """Tira screenshot para debug/auditoria."""
        if not self.rpa_config.screenshots_enabled:
            return None
        
        try:
            storage_path = Path(self.rpa_config.storage_path) / "screenshots" / self.run_id
            storage_path.mkdir(parents=True, exist_ok=True)
            
            filepath = storage_path / f"{name}_{datetime.utcnow().strftime('%H%M%S')}.png"
            await self._page.screenshot(path=str(filepath))
            return str(filepath)
        except Exception as e:
            logger.warning("Erro ao tirar screenshot: %s", e)
            return None
    
    async def detect_captcha(self) -> bool:
        """Detecta presença de CAPTCHA na página."""
        captcha_selectors = [
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            ".g-recaptcha",
            "#captcha",
            "[data-captcha]",
        ]
        
        for selector in captcha_selectors:
            try:
                element = await self._page.query_selector(selector)
                if element:
                    self.metrics.captcha_encountered = True
                    logger.warning("CAPTCHA detectado: %s", selector)
                    return True
            except Exception:
                pass
        
        return False
    
    # Métodos abstratos que cada portal deve implementar
    
    @abstractmethod
    async def login(self, job: JobConfig) -> bool:
        """
        Realiza login no portal.
        Deve usar job.credentials_secret_id para obter credenciais.
        """
        pass
    
    @abstractmethod
    async def navigate_to_list(self, job: JobConfig):
        """Navega até a listagem de cotações."""
        pass
    
    @abstractmethod
    async def get_quote_list(self, job: JobConfig) -> list[Any]:
        """
        Retorna lista de referências de cotações (IDs, URLs, elementos).
        Aplica filtros de job.filters.
        """
        pass
    
    @abstractmethod
    async def capture_quote_detail(self, quote_ref: Any, job: JobConfig) -> Optional[CapturedQuote]:
        """Captura detalhes de uma cotação específica."""
        pass
