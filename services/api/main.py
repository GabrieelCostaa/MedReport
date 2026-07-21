import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Structured logging with structlog + OpenTelemetry trace IDs
from app.core.logging_config import setup_logging, setup_opentelemetry
setup_logging()

from app.api import auth, reports, tuss, quotes, ai, erp_mock, notifications, products, glosas
from app.core.config import settings
from app.db.init_db import create_tables, seed

limiter = Limiter(key_func=get_remote_address)


async def _auto_etl_if_empty():
    """
    Auto-popula tabelas TUSS/ANVISA se estiverem vazias.
    Roda em background — não bloqueia o startup.
    Garante que o sistema nunca fique sem dados regulatórios.
    """
    import asyncio as _aio
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, func
    from app.db.session import AsyncSessionLocal
    from app.db.models import (
        TussMaterial, TussProcedure, AnvisaProduct,
        GlosaMotivo, OperadoraGlosaIndicador,
    )

    try:
        async with AsyncSessionLocal() as db:
            tuss_count = (await db.execute(select(func.count(TussMaterial.codigo_tuss)))).scalar()
            anvisa_count = (await db.execute(select(func.count(AnvisaProduct.id)))).scalar()
            glosa_motivos_count = (await db.execute(select(func.count(GlosaMotivo.codigo)))).scalar()
            glosa_panel_count = (await db.execute(select(func.count(OperadoraGlosaIndicador.id)))).scalar()
            glosa_panel_last = (await db.execute(select(func.max(OperadoraGlosaIndicador.created_at)))).scalar()

        tasks = []

        if tuss_count < 100:
            logging.getLogger("startup").info("TUSS vazio (%d) — baixando da ANS em background...", tuss_count)
            async def _load_tuss():
                try:
                    from scripts.etl.download_tuss import run_etl
                    async with AsyncSessionLocal() as db:
                        result = await run_etl(db_session=db)
                        logging.getLogger("startup").info("TUSS carregado: %s", result)
                except Exception as e:
                    logging.getLogger("startup").warning("Auto-ETL TUSS falhou: %s", e)
            tasks.append(_load_tuss())

        if anvisa_count < 100:
            logging.getLogger("startup").info("ANVISA vazio (%d) — baixando dados abertos em background...", anvisa_count)
            async def _load_anvisa():
                try:
                    from scripts.etl.download_anvisa import run_etl
                    async with AsyncSessionLocal() as db:
                        result = await run_etl(db_session=db)
                        logging.getLogger("startup").info("ANVISA carregado: %s", result)
                except Exception as e:
                    logging.getLogger("startup").warning("Auto-ETL ANVISA falhou: %s", e)
            tasks.append(_load_anvisa())
        else:
            # Base já populada: garante que search_normalized existe nos legados
            # (o ETL só re-roda se a tabela estiver vazia). Backfill idempotente.
            async def _backfill_anvisa_search():
                try:
                    async with AsyncSessionLocal() as db:
                        pending = (await db.execute(
                            select(func.count(AnvisaProduct.id))
                            .where(AnvisaProduct.search_normalized.is_(None))
                        )).scalar()
                        if pending and pending > 0:
                            from scripts.etl.download_anvisa import backfill_search_normalized
                            logging.getLogger("startup").info(
                                "ANVISA: backfill de search_normalized em %d registros...", pending)
                            r = await backfill_search_normalized(db)
                            logging.getLogger("startup").info("ANVISA backfill: %s", r)
                except Exception as e:
                    logging.getLogger("startup").warning("Backfill ANVISA falhou: %s", e)
            tasks.append(_backfill_anvisa_search())

        if glosa_motivos_count < 10:
            logging.getLogger("startup").info(
                "Tabela 38 vazia (%d) — carregando do arquivo do repo...", glosa_motivos_count)
            async def _load_tabela38():
                try:
                    from scripts.etl.ingest_tabela38 import run_etl
                    async with AsyncSessionLocal() as db:
                        result = await run_etl(db_session=db)
                        logging.getLogger("startup").info("Tabela 38 carregada: %s", result)
                except Exception as e:
                    logging.getLogger("startup").warning("Auto-ETL Tabela 38 falhou: %s", e)
            tasks.append(_load_tabela38())

        # Painel de Glosas: carrega se vazio OU refresh mensal (snapshot ~8,5MB)
        panel_stale = False
        if glosa_panel_last is not None:
            last = glosa_panel_last
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            panel_stale = datetime.now(timezone.utc) - last > timedelta(days=30)
        if glosa_panel_count < 100 or panel_stale:
            motivo = "vazio" if glosa_panel_count < 100 else "desatualizado (>30 dias)"
            logging.getLogger("startup").info(
                "Painel de Glosas %s — baixando dados abertos da ANS em background...", motivo)
            async def _load_glosa_panel():
                try:
                    from scripts.etl.download_glosa_panel import run_etl
                    async with AsyncSessionLocal() as db:
                        result = await run_etl(db_session=db)
                        logging.getLogger("startup").info("Painel de Glosas carregado: %s", result)
                except Exception as e:
                    logging.getLogger("startup").warning("Auto-ETL Painel de Glosas falhou: %s", e)
            tasks.append(_load_glosa_panel())

        if tasks:
            await _aio.gather(*tasks)
        else:
            logging.getLogger("startup").info(
                "Dados regulatórios OK (TUSS=%d, ANVISA=%d, Tab38=%d, PainelGlosas=%d)",
                tuss_count, anvisa_count, glosa_motivos_count, glosa_panel_count,
            )

    except Exception as e:
        logging.getLogger("startup").warning("Auto-ETL check falhou (non-blocking): %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await seed()
    # Auto-populate regulatory data in background if empty
    # Skip on low-memory environments (Render free tier = 512MB)
    import os
    if os.environ.get("SKIP_AUTO_ETL") != "true":
        import asyncio as _aio
        _aio.create_task(_auto_etl_if_empty())
    else:
        logging.getLogger("startup").info("Auto-ETL skipped (SKIP_AUTO_ETL=true)")
    yield


app = FastAPI(
    lifespan=lifespan,
    title="OPME Platform API",
    description="API para relatórios cirúrgicos TISS/TUSS e cotações",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# OpenTelemetry instrumentation (auto-traces all endpoints)
setup_opentelemetry(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(auth.token_router, prefix="/auth", tags=["token"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(tuss.router, prefix="/api/tuss", tags=["tuss"])
app.include_router(glosas.router, prefix="/api/glosas", tags=["glosas"])
app.include_router(quotes.router, prefix="/api/quotes", tags=["quotes"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(products.router, prefix="/api/products", tags=["products"])
app.include_router(erp_mock.router)
app.include_router(notifications.router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Knowledge Graph endpoints
@app.get("/api/graph/query")
async def graph_query(
    cid: str,
    product_id: str = "",
    max_depth: int = 3,
):
    """Query the medical knowledge graph for a CID + product."""
    from app.services.knowledge_graph import query_knowledge_graph, format_graph_context_for_llm
    from app.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as db:
        ctx = await query_knowledge_graph(db, cid, product_id, max_depth)
    return {
        "cid": cid,
        "product_id": product_id,
        "stats": ctx.graph_stats,
        "procedures": ctx.procedures,
        "evidences": len(ctx.clinical_evidences),
        "articles": len(ctx.pubmed_articles),
        "regulatory": ctx.regulatory,
        "umls": ctx.umls_concepts,
        "snomed": ctx.snomed_concepts,
        "path": ctx.cid_product_path,
        "llm_context": format_graph_context_for_llm(ctx),
    }


@app.get("/api/graph/stats")
async def graph_stats():
    """Return knowledge graph statistics."""
    from app.services.knowledge_graph import get_graph
    G = get_graph()
    if G is None:
        return {"loaded": False, "nodes": 0, "edges": 0}
    try:
        import networkx as nx
        node_types = dict(sorted(
            {t: 0 for t in set(nx.get_node_attributes(G, "semantic_type").values())}.items()
        )) if G.number_of_nodes() > 0 else {}
    except ImportError:
        node_types = {}
    return {
        "loaded": True,
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "node_types": node_types,
    }
