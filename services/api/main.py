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

from app.api import auth, reports, tuss, quotes, ai, erp_mock, notifications, products
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
    from sqlalchemy import select, func
    from app.db.session import AsyncSessionLocal
    from app.db.models import TussMaterial, TussProcedure, AnvisaProduct

    try:
        async with AsyncSessionLocal() as db:
            tuss_count = (await db.execute(select(func.count(TussMaterial.codigo_tuss)))).scalar()
            anvisa_count = (await db.execute(select(func.count(AnvisaProduct.id)))).scalar()

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

        if tasks:
            await _aio.gather(*tasks)
        else:
            logging.getLogger("startup").info("Dados regulatórios OK (TUSS=%d, ANVISA=%d)", tuss_count, anvisa_count)

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
