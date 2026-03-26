import ssl
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

# Neon.tech / cloud PostgreSQL requires SSL
_connect_args = {}
_db_url = settings.DATABASE_URL
if "neon.tech" in _db_url or "sslmode=require" in _db_url:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    _connect_args = {"ssl": ssl_ctx}
    # asyncpg doesn't accept sslmode/channel_binding as URL params — strip them
    import re
    _db_url = re.sub(r"[?&](sslmode|channel_binding)=[^&]*", "", _db_url)
    _db_url = _db_url.rstrip("?&")

engine = create_async_engine(
    _db_url,
    echo=False,
    connect_args=_connect_args,
)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
