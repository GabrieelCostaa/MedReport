from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import TussTerm
from app.services.tuss_search import search_tuss

router = APIRouter()


@router.get("/search")
async def tuss_search(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
):
    """Busca termos TUSS por descrição (usa Elasticsearch se disponível, senão PostgreSQL)."""
    items = await search_tuss(db, q)
    return {"items": [{"code": i["code"], "term": i["term"]} for i in items]}


@router.get("/code/{code}")
async def tuss_by_code(
    code: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TussTerm).where(TussTerm.code == code).limit(1))
    t = result.scalar_one_or_none()
    if not t:
        return {"code": code, "term": ""}
    return {"code": t.code, "term": t.term}
