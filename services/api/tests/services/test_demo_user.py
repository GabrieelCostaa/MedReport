"""Usuário de demonstração (senha pública no repositório) nunca pode valer fora do banco local."""
import pytest

import app.db.init_db as init_db
from app.core.security import verify_password


class TestDemoUserAllowed:
    @pytest.mark.parametrize("url", [
        "postgresql+asyncpg://opme:opme_dev_secret@localhost:5432/opme",
        "postgresql+asyncpg://opme:x@127.0.0.1:55432/opme",
        "sqlite+aiosqlite:///./opme_dev.db",
        "postgresql+asyncpg://opme:x@postgres:5432/opme",
    ])
    def test_local_permite(self, url):
        assert init_db.demo_user_allowed(database_url=url, flag=None) is True

    @pytest.mark.parametrize("url", [
        "postgresql+asyncpg://u:p@ep-cool-name-123.sa-east-1.aws.neon.tech/medreport?ssl=true",
        "postgresql+asyncpg://u:p@dpg-abc.oregon-postgres.render.com/medreport",
        "",
    ])
    def test_remoto_bloqueia(self, url):
        assert init_db.demo_user_allowed(database_url=url, flag=None) is False

    def test_flag_explicita_vence(self):
        neon = "postgresql+asyncpg://u:p@x.neon.tech/db"
        assert init_db.demo_user_allowed(database_url=neon, flag=True) is True
        assert init_db.demo_user_allowed(database_url="sqlite://", flag=False) is False


@pytest.fixture
async def sqlite_db(monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from app.db.session import Base
    import app.db.models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(init_db, "AsyncSessionLocal", Session)
    yield Session
    await engine.dispose()


async def _demo_user(Session):
    from sqlalchemy import select
    from app.db.models import User
    async with Session() as db:
        return (await db.execute(select(User).where(User.email == init_db.DEMO_EMAIL))).scalar_one_or_none()


async def _count(Session, model):
    from sqlalchemy import select, func
    async with Session() as db:
        return (await db.execute(select(func.count()).select_from(model))).scalar()


async def test_seed_em_producao_nao_cria_demo_mas_cria_catalogo(sqlite_db, monkeypatch):
    from app.db.models import Product
    monkeypatch.setattr(init_db, "demo_user_allowed", lambda *a, **k: False)
    await init_db.seed()
    assert await _demo_user(sqlite_db) is None
    n = await _count(sqlite_db, Product)
    assert n > 0
    # segunda subida: não duplica o catálogo (antes o marcador era o usuário demo)
    await init_db.seed()
    assert await _count(sqlite_db, Product) == n


async def test_seed_local_cria_demo(sqlite_db, monkeypatch):
    monkeypatch.setattr(init_db, "demo_user_allowed", lambda *a, **k: True)
    await init_db.seed()
    user = await _demo_user(sqlite_db)
    assert user is not None
    assert verify_password(init_db.DEMO_PASSWORD, user.hashed_password)


async def test_producao_invalida_senha_publica_existente(sqlite_db, monkeypatch):
    # banco "antigo": seed criou o demo com a senha pública
    monkeypatch.setattr(init_db, "demo_user_allowed", lambda *a, **k: True)
    await init_db.seed()
    # agora o mesmo banco sobe como produção
    monkeypatch.setattr(init_db, "demo_user_allowed", lambda *a, **k: False)
    assert await init_db.disable_demo_user_if_not_allowed() is True
    user = await _demo_user(sqlite_db)
    assert user is not None  # não apaga (pode ter laudos ligados)
    assert not verify_password(init_db.DEMO_PASSWORD, user.hashed_password)
    assert await init_db.disable_demo_user_if_not_allowed() is False  # idempotente


async def test_local_nao_mexe_no_demo(sqlite_db, monkeypatch):
    monkeypatch.setattr(init_db, "demo_user_allowed", lambda *a, **k: True)
    await init_db.seed()
    assert await init_db.disable_demo_user_if_not_allowed() is False
    user = await _demo_user(sqlite_db)
    assert verify_password(init_db.DEMO_PASSWORD, user.hashed_password)
