"""
Orquestrador de jobs RPA.
Gerencia fila de execução, concorrência e integração com API.
"""
import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional
import json

try:
    from core.base_bot import BaseBot, CapturedQuote, JobConfig
    from core.circuit_breaker import CircuitBreakerRegistry
    from core.config import RpaConfig, DEFAULT_CONFIG
    from core.metrics import GLOBAL_METRICS
except ImportError:
    from .base_bot import BaseBot, CapturedQuote, JobConfig
    from .circuit_breaker import CircuitBreakerRegistry
    from .config import RpaConfig, DEFAULT_CONFIG
    from .metrics import GLOBAL_METRICS

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Representa um job de coleta."""
    id: str
    config: JobConfig
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class RpaOrchestrator:
    """
    Orquestrador de jobs RPA.
    
    Responsabilidades:
    - Gerenciar fila de jobs
    - Controlar concorrência por portal
    - Executar bots e coletar resultados
    - Enviar resultados para API
    """
    
    def __init__(
        self,
        rpa_config: Optional[RpaConfig] = None,
        bot_factory: Optional[Callable[[str], BaseBot]] = None,
    ):
        self.config = rpa_config or DEFAULT_CONFIG
        self.bot_factory = bot_factory or self._default_bot_factory
        self._jobs: dict[str, Job] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._semaphores: dict[str, asyncio.Semaphore] = {}
    
    def _default_bot_factory(self, portal: str) -> BaseBot:
        """Factory padrão de bots."""
        try:
            from portals.demo_portal import DemoPortalBot
            from portals.generic_portal import GenericPortalBot
            from core.config import PortalConfig
        except ImportError:
            from ..portals.demo_portal import DemoPortalBot
            from ..portals.generic_portal import GenericPortalBot
            from .config import PortalConfig
        
        if portal == "demo":
            return DemoPortalBot()
        
        config = PortalConfig(
            name=portal,
            display_name=portal.title(),
            base_url=f"https://{portal}.example.com",
        )
        return GenericPortalBot(config)
    
    def _get_portal_semaphore(self, portal: str) -> asyncio.Semaphore:
        """Obtém semáforo de concorrência por portal."""
        if portal not in self._semaphores:
            self._semaphores[portal] = asyncio.Semaphore(2)
        return self._semaphores[portal]
    
    async def start(self, num_workers: int = 3):
        """Inicia orquestrador com workers."""
        if self._running:
            return
        
        self._running = True
        logger.info("Iniciando orquestrador com %d workers", num_workers)
        
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)
    
    async def stop(self):
        """Para orquestrador."""
        self._running = False
        
        for worker in self._workers:
            worker.cancel()
        
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        
        logger.info("Orquestrador parado")
    
    async def submit_job(self, config: JobConfig) -> str:
        """Submete novo job para execução."""
        job_id = str(uuid.uuid4())
        job = Job(id=job_id, config=config)
        self._jobs[job_id] = job
        
        await self._queue.put(job_id)
        logger.info("Job %s submetido (portal=%s)", job_id, config.portal)
        
        return job_id
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Obtém status de um job."""
        return self._jobs.get(job_id)
    
    def list_jobs(self, status: Optional[JobStatus] = None) -> list[Job]:
        """Lista jobs, opcionalmente filtrados por status."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
    
    async def _worker(self, worker_id: int):
        """Worker que processa jobs da fila."""
        logger.info("Worker %d iniciado", worker_id)
        
        while self._running:
            try:
                job_id = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=5.0
                )
                
                job = self._jobs.get(job_id)
                if not job or job.status == JobStatus.CANCELLED:
                    continue
                
                await self._execute_job(job)
                
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Erro no worker %d: %s", worker_id, e)
    
    async def _execute_job(self, job: Job):
        """Executa um job."""
        portal = job.config.portal
        semaphore = self._get_portal_semaphore(portal)
        
        async with semaphore:
            job.status = JobStatus.RUNNING
            job.started_at = datetime.utcnow()
            
            logger.info("Executando job %s (portal=%s)", job.id, portal)
            
            try:
                bot = self.bot_factory(portal)
                quotes = await bot.execute(job.config)
                
                job.status = JobStatus.SUCCESS
                job.result = {
                    "quotes_count": len(quotes),
                    "items_count": sum(len(q.items) for q in quotes),
                    "quotes": [self._quote_to_dict(q) for q in quotes],
                }
                
                await self._send_to_api(quotes, job)
                
            except Exception as e:
                logger.exception("Job %s falhou: %s", job.id, e)
                job.status = JobStatus.FAILED
                job.error = str(e)
            
            finally:
                job.finished_at = datetime.utcnow()
    
    def _quote_to_dict(self, quote: CapturedQuote) -> dict:
        """Converte CapturedQuote para dict."""
        return {
            "external_id": quote.external_id,
            "portal": quote.portal,
            "status": quote.status,
            "published_at": quote.published_at,
            "deadline_at": quote.deadline_at,
            "buyer_name": quote.buyer_name,
            "buyer_type": quote.buyer_type,
            "delivery_city": quote.delivery_city,
            "delivery_state": quote.delivery_state,
            "items": quote.items,
            "attachments": quote.attachments,
        }
    
    async def _send_to_api(self, quotes: list[CapturedQuote], job: Job):
        """Envia cotações para API."""
        if not self.config.api_token or not quotes:
            return
        
        try:
            import httpx
            
            payload = {
                "quotes": [
                    {
                        "tenant_id": job.config.tenant_id,
                        "external_id": q.external_id,
                        "portal": q.portal,
                        "status": q.status,
                        "published_at": q.published_at,
                        "deadline": q.deadline_at,
                        "buyer": {
                            "name": q.buyer_name,
                            "type": q.buyer_type,
                        },
                        "delivery": {
                            "city": q.delivery_city,
                            "state": q.delivery_state,
                        },
                        "items": q.items,
                        "attachments": q.attachments,
                        "rpa_run": {
                            "run_id": job.id,
                        },
                    }
                    for q in quotes
                ]
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.config.api_url}/api/quotes/ingest",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.config.api_token}"},
                    timeout=30,
                )
                response.raise_for_status()
                
            logger.info("Enviadas %d cotações para API", len(quotes))
            
        except Exception as e:
            logger.exception("Erro ao enviar para API: %s", e)


async def run_single_job(config: JobConfig) -> list[CapturedQuote]:
    """Executa um único job sem orquestrador."""
    orchestrator = RpaOrchestrator()
    bot = orchestrator.bot_factory(config.portal)
    return await bot.execute(config)
