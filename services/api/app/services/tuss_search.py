"""Busca TUSS: tenta Elasticsearch, fallback para PostgreSQL."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TussTerm


async def search_tuss(db: AsyncSession, query: str, limit: int = 10) -> list[dict]:
    """Busca termos na tabela TUSS por texto. Fallback para ILIKE no PostgreSQL."""
    q = f"%{query.strip()}%"
    result = await db.execute(
        select(TussTerm.code, TussTerm.term)
        .where(TussTerm.term.ilike(q))
        .limit(limit)
    )
    rows = result.all()
    return [{"code": r.code, "term": r.term} for r in rows]
