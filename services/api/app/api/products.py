"""API de Produtos OPME."""
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.db.models import Product
from app.core.security import get_current_user_id

router = APIRouter()


@router.get("")
async def list_products(
    q: Optional[str] = Query(None, description="Busca por nome ou linha"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Lista produtos OPME com busca opcional."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    query = select(Product)
    if q:
        query = query.where(
            Product.nome.ilike(f"%{q}%") | Product.linha.ilike(f"%{q}%")
        )
    query = query.order_by(Product.nome)
    result = await db.execute(query)
    products = result.scalars().all()

    return {
        "items": [
            {
                "id": str(p.id),
                "nome": p.nome,
                "linha": p.linha,
                "descricao_tecnica": (p.descricao_tecnica or "")[:200],
                "diferenciais_clinicos": (p.diferenciais_clinicos or "")[:200],
                "codigo_tuss_sugerido": p.codigo_tuss_sugerido,
                "registro_anvisa": p.registro_anvisa,
            }
            for p in products
        ]
    }


@router.get("/{product_id}")
async def get_product(
    product_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Detalhes completos de um produto (verdades absolutas)."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    result = await db.execute(select(Product).where(Product.id == product_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "id": str(p.id),
        "nome": p.nome,
        "linha": p.linha,
        "descricao_tecnica": p.descricao_tecnica,
        "diferenciais_clinicos": p.diferenciais_clinicos,
        "indicacoes": p.indicacoes,
        "contraindicacoes": p.contraindicacoes,
        "viscosidade": p.viscosidade,
        "peso_molecular": p.peso_molecular,
        "concentracao": p.concentracao,
        "registro_anvisa": p.registro_anvisa,
        "codigo_tuss_sugerido": p.codigo_tuss_sugerido,
        "bula_url": p.bula_url,
        "referencias_bibliograficas": p.referencias_bibliograficas,
    }
