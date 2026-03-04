"""
Métricas e observabilidade para RPA.
"""
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


@dataclass
class RunMetrics:
    """Métricas de uma execução RPA."""
    run_id: str
    portal: str
    tenant_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    status: str = "running"
    # Contadores
    quotes_found: int = 0
    quotes_new: int = 0
    items_captured: int = 0
    attachments_downloaded: int = 0
    pages_visited: int = 0
    # Problemas
    captcha_encountered: bool = False
    login_failed: bool = False
    errors: list[str] = field(default_factory=list)
    # Timing
    login_duration_ms: Optional[int] = None
    navigation_duration_ms: Optional[int] = None
    capture_duration_ms: Optional[int] = None
    total_duration_ms: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "portal": self.portal,
            "tenant_id": self.tenant_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "status": self.status,
            "quotes_found": self.quotes_found,
            "quotes_new": self.quotes_new,
            "items_captured": self.items_captured,
            "attachments_downloaded": self.attachments_downloaded,
            "pages_visited": self.pages_visited,
            "captcha_encountered": self.captcha_encountered,
            "login_failed": self.login_failed,
            "errors": self.errors,
            "login_duration_ms": self.login_duration_ms,
            "navigation_duration_ms": self.navigation_duration_ms,
            "capture_duration_ms": self.capture_duration_ms,
            "total_duration_ms": self.total_duration_ms,
        }


class MetricsCollector:
    """Coletor de métricas agregadas."""
    
    def __init__(self):
        self._runs: dict[str, RunMetrics] = {}
        self._portal_stats: dict[str, dict] = defaultdict(lambda: {
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "total_quotes": 0,
            "total_items": 0,
            "captcha_count": 0,
            "login_failures": 0,
            "avg_duration_ms": 0,
            "last_run_at": None,
        })
    
    def start_run(self, run_id: str, portal: str, tenant_id: Optional[str] = None) -> RunMetrics:
        """Inicia coleta de métricas para uma execução."""
        metrics = RunMetrics(
            run_id=run_id,
            portal=portal,
            tenant_id=tenant_id,
            started_at=datetime.utcnow(),
        )
        self._runs[run_id] = metrics
        logger.info("RPA run started: %s (portal=%s)", run_id, portal)
        return metrics
    
    def finish_run(self, run_id: str, status: str = "success"):
        """Finaliza coleta de métricas."""
        if run_id not in self._runs:
            return
        
        metrics = self._runs[run_id]
        metrics.finished_at = datetime.utcnow()
        metrics.status = status
        
        if metrics.started_at:
            metrics.total_duration_ms = int(
                (metrics.finished_at - metrics.started_at).total_seconds() * 1000
            )
        
        self._update_portal_stats(metrics)
        
        logger.info(
            "RPA run finished: %s (status=%s, quotes=%d, duration=%dms)",
            run_id, status, metrics.quotes_found, metrics.total_duration_ms or 0
        )
    
    def _update_portal_stats(self, metrics: RunMetrics):
        """Atualiza estatísticas agregadas do portal."""
        stats = self._portal_stats[metrics.portal]
        stats["total_runs"] += 1
        stats["last_run_at"] = metrics.finished_at.isoformat() if metrics.finished_at else None
        
        if metrics.status == "success":
            stats["successful_runs"] += 1
        else:
            stats["failed_runs"] += 1
        
        stats["total_quotes"] += metrics.quotes_found
        stats["total_items"] += metrics.items_captured
        
        if metrics.captcha_encountered:
            stats["captcha_count"] += 1
        if metrics.login_failed:
            stats["login_failures"] += 1
        
        if metrics.total_duration_ms:
            n = stats["total_runs"]
            old_avg = stats["avg_duration_ms"]
            stats["avg_duration_ms"] = old_avg + (metrics.total_duration_ms - old_avg) / n
    
    def get_run(self, run_id: str) -> Optional[RunMetrics]:
        """Obtém métricas de uma execução."""
        return self._runs.get(run_id)
    
    def get_portal_stats(self, portal: str) -> dict:
        """Obtém estatísticas de um portal."""
        return dict(self._portal_stats[portal])
    
    def get_all_stats(self) -> dict:
        """Obtém todas as estatísticas."""
        return {
            "portals": {k: dict(v) for k, v in self._portal_stats.items()},
            "active_runs": len([r for r in self._runs.values() if r.status == "running"]),
            "total_runs": sum(s["total_runs"] for s in self._portal_stats.values()),
        }


class Timer:
    """Context manager para medir tempo."""
    
    def __init__(self, name: str = "operation"):
        self.name = name
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
    
    def __enter__(self):
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, *args):
        self.end_time = time.perf_counter()
    
    @property
    def elapsed_ms(self) -> int:
        if self.start_time is None:
            return 0
        end = self.end_time or time.perf_counter()
        return int((end - self.start_time) * 1000)
    
    def log(self):
        logger.debug("%s completed in %dms", self.name, self.elapsed_ms)


GLOBAL_METRICS = MetricsCollector()
