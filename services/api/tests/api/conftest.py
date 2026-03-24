"""
Fixtures de integração para testes de API.
Usa SQLite in-memory para isolamento total — sem dependência de PostgreSQL.
"""
import sys
import os
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Garante que o módulo app é importável
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.db.session import Base, get_db
from app.db.models import User, Product, AnvisaProduct, TussMaterial, TussTerm
from app.core.security import get_password_hash, create_access_token


# ── Engine SQLite async (in-memory, compartilhado entre conexões) ──
TEST_DB_URL = "sqlite+aiosqlite:///file:testdb?mode=memory&cache=shared&uri=true"

engine = create_async_engine(TEST_DB_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Cria todas as tabelas antes de cada teste e limpa depois."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db():
    """Sessão de banco para inserir dados de teste."""
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    """httpx AsyncClient apontando para o app FastAPI com DB de teste."""
    from main import app
    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Dados de teste ──

TEST_PASSWORD = "Senha_Segura_123"


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Cria um usuário médico no banco de teste."""
    user = User(
        id=uuid.uuid4(),
        email="dr.teste@medreport.com",
        hashed_password=get_password_hash(TEST_PASSWORD),
        role="medico",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user: User) -> dict:
    """Headers com Bearer token válido para o test_user."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def test_product(db: AsyncSession) -> Product:
    """Produto OPME de teste no catálogo interno."""
    product = Product(
        id=uuid.uuid4(),
        nome="Prótese de Joelho Modelo X",
        linha="Ortopedia",
        descricao_tecnica="Prótese total de joelho em titânio com polietileno",
        registro_anvisa="80197000001",
        codigo_tuss_sugerido="30715016",
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@pytest_asyncio.fixture
async def test_anvisa_product(db: AsyncSession) -> AnvisaProduct:
    """Registro ANVISA de teste (não importado para o catálogo)."""
    ap = AnvisaProduct(
        id=uuid.uuid4(),
        registro="80197000099",
        nome_comercial="Parafuso Ósseo ABC",
        fabricante="Fabricante XYZ",
        nome_tecnico="Parafuso para fixação óssea em titânio",
        status="ativo",
        classe_risco="III",
    )
    db.add(ap)
    await db.commit()
    await db.refresh(ap)
    return ap


@pytest_asyncio.fixture
async def test_tuss_material(db: AsyncSession, test_anvisa_product: AnvisaProduct) -> TussMaterial:
    """Material TUSS mapeado ao produto ANVISA de teste."""
    tm = TussMaterial(
        codigo_tuss="60011120",
        nome="Parafuso ósseo titânio 3.5mm",
        registro_anvisa=test_anvisa_product.registro,
        subgrupo="Implantes Ortopédicos",
        ativo=True,
    )
    db.add(tm)
    await db.commit()
    return tm


@pytest_asyncio.fixture
async def test_tuss_term(db: AsyncSession) -> TussTerm:
    """Termo TUSS válido para testes de review."""
    term = TussTerm(
        id=uuid.uuid4(),
        code="30715016",
        term="Artroplastia total do joelho",
    )
    db.add(term)
    await db.commit()
    return term
