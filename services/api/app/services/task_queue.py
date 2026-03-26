"""
Background task queue with TaskIQ + Redis.

Provides async-first task execution for:
  - Batch report generation
  - PubMed cache warm-up
  - ANVISA data sync
  - PDF generation (offload from request)

Fallback to in-process execution when Redis/TaskIQ unavailable.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── TaskIQ Broker (lazy init) ─────────────────────────────────────────────

_broker = None
_TASKIQ_AVAILABLE: Optional[bool] = None


def get_broker():
    """Get or create TaskIQ Redis broker."""
    global _broker, _TASKIQ_AVAILABLE
    if _TASKIQ_AVAILABLE is False:
        return None
    if _broker is not None:
        return _broker
    try:
        from taskiq_redis import ListQueueBroker
        from app.core.config import settings
        _broker = ListQueueBroker(url=settings.REDIS_URL)
        _TASKIQ_AVAILABLE = True
        logger.info("TaskIQ broker connected: %s", settings.REDIS_URL)
        return _broker
    except Exception as e:
        _TASKIQ_AVAILABLE = False
        logger.debug("TaskIQ unavailable, tasks will run in-process: %s", e)
        return None


# ── Task Definitions ──────────────────────────────────────────────────────

# These are defined as regular async functions.
# When TaskIQ is available, they run in a worker process.
# When not, they run in-process via asyncio.create_task().

async def warm_pubmed_cache(cid: str, product_name: str = ""):
    """Pre-warm PubMed cache for a CID (background)."""
    try:
        from app.db.session import AsyncSessionLocal
        from app.services.pubmed_service import get_evidences_for_cid
        async with AsyncSessionLocal() as db:
            evidences = await get_evidences_for_cid(db, cid, product_name)
            await db.commit()
            logger.info("PubMed cache warmed for CID %s: %d evidences", cid, len(evidences))
            return len(evidences)
    except Exception as e:
        logger.warning("PubMed cache warm-up failed for CID %s: %s", cid, e)
        return 0


async def sync_anvisa_registro(registro: str):
    """Sync a single ANVISA registration (background)."""
    try:
        from app.db.session import AsyncSessionLocal
        from app.services.anvisa_service import consultar_registro
        async with AsyncSessionLocal() as db:
            result = await consultar_registro(db, registro)
            await db.commit()
            logger.info("ANVISA sync for %s: %s (%s)", registro, result.status, result.fonte)
            return {"registro": registro, "status": result.status, "fonte": result.fonte}
    except Exception as e:
        logger.warning("ANVISA sync failed for %s: %s", registro, e)
        return {"registro": registro, "error": str(e)}


async def generate_report_background(
    user_id: str,
    product_id: str,
    cid: str,
    diagnostico: str,
    paciente_nome: str = "",
    **kwargs,
) -> dict:
    """Generate a report in background (for batch processing)."""
    try:
        from uuid import UUID
        from sqlalchemy import select
        from app.db.session import AsyncSessionLocal
        from app.db.models import Product, ReportTemplate
        from app.services.agents.pipeline import ReportPipeline

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Product).where(Product.id == UUID(product_id)))
            product = result.scalar_one_or_none()
            if not product:
                return {"error": f"Product {product_id} not found"}

            template_result = await db.execute(
                select(ReportTemplate).where(ReportTemplate.produto_id == product.id).limit(1)
            )
            template = template_result.scalar_one_or_none()

            medico_inputs = {
                "paciente_nome": paciente_nome,
                "cid": cid,
                "diagnostico": diagnostico,
                **kwargs,
            }

            pipeline_result = await ReportPipeline.start(
                product=product,
                template=template,
                diagnostico=diagnostico,
                cid=cid,
                medico_inputs=medico_inputs,
                db=db,
                user_id=user_id,
            )
            await db.commit()
            return pipeline_result

    except Exception as e:
        logger.exception("Background report generation failed: %s", e)
        return {"error": str(e)}


# ── Dispatcher ────────────────────────────────────────────────────────────

async def dispatch(task_fn, *args, **kwargs):
    """
    Dispatch a task to TaskIQ worker or run in-process.

    Usage:
        await dispatch(warm_pubmed_cache, "M17.0", "Synvisc")
    """
    broker = get_broker()
    if broker:
        try:
            # TaskIQ: send to worker
            task = broker.task(task_fn)
            result = await task.kiq(*args, **kwargs)
            logger.info("Task dispatched to TaskIQ: %s", task_fn.__name__)
            return result
        except Exception as e:
            logger.warning("TaskIQ dispatch failed, running in-process: %s", e)

    # Fallback: run in-process
    import asyncio
    asyncio.create_task(task_fn(*args, **kwargs))
    logger.info("Task running in-process: %s", task_fn.__name__)
