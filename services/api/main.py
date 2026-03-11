from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, reports, tuss, quotes, ai, erp_mock, notifications, products
from app.core.config import settings
from app.db.init_db import create_tables, seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    await seed()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="OPME Platform API",
    description="API para relatórios cirúrgicos TISS/TUSS e cotações",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
