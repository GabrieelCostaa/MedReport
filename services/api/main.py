import logging
import logging.config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
})

from app.api import auth, reports, tuss, quotes, ai, erp_mock, notifications, products
from app.core.config import settings
from app.db.init_db import create_tables, seed

limiter = Limiter(key_func=get_remote_address)


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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
