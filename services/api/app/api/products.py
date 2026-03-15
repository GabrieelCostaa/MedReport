"""API de Produtos OPME — busca em catálogo interno + base ANVISA (96k+ registros)."""
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.session import get_db
from app.db.models import Product, AnvisaProduct
from app.core.security import get_current_user_id

router = APIRouter()


class QuickProductIn(BaseModel):
    nome: str
    registro_anvisa: Optional[str] = None
    fabricante: Optional[str] = None
    codigo_tuss_sugerido: Optional[str] = None


@router.get("")
async def list_products(
    q: Optional[str] = Query(None, description="Busca por nome ou linha"),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Lista produtos: primeiro catálogo interno, depois base ANVISA."""
    # TODO: re-enable auth when ready

    # 1) Busca no catálogo interno (products)
    query = select(Product)
    if q:
        query = query.where(
            Product.nome.ilike(f"%{q}%") | Product.linha.ilike(f"%{q}%")
        )
    query = query.order_by(Product.nome).limit(20)
    result = await db.execute(query)
    catalog_products = result.scalars().all()

    items = [
        {
            "id": str(p.id),
            "nome": p.nome,
            "linha": p.linha,
            "descricao_tecnica": (p.descricao_tecnica or "")[:200],
            "diferenciais_clinicos": (p.diferenciais_clinicos or "")[:200],
            "codigo_tuss_sugerido": p.codigo_tuss_sugerido,
            "registro_anvisa": p.registro_anvisa,
            "source": "catalog",
        }
        for p in catalog_products
    ]

    # 2) Se tem busca e poucos resultados internos, busca na base ANVISA
    if q and len(items) < 10:
        anvisa_limit = 20 - len(items)
        # Quebra a query em palavras para busca mais flexível
        words = [w.strip() for w in q.split() if len(w.strip()) >= 2]

        if words:
            # Todas as palavras devem aparecer no nome comercial
            conditions = [AnvisaProduct.nome_comercial.ilike(f"%{w}%") for w in words]
            anvisa_query = (
                select(AnvisaProduct)
                .where(*conditions)
                .where(AnvisaProduct.status == "ativo")
                .order_by(AnvisaProduct.nome_comercial)
                .limit(anvisa_limit)
            )
            anvisa_result = await db.execute(anvisa_query)
            anvisa_products = anvisa_result.scalars().all()

            # Excluir registros ANVISA que já existem no catálogo interno
            catalog_anvisa_ids = {p.registro_anvisa for p in catalog_products if p.registro_anvisa}

            for ap in anvisa_products:
                if ap.registro in catalog_anvisa_ids:
                    continue
                items.append({
                    "id": f"anvisa:{ap.registro}",
                    "nome": ap.nome_comercial or f"Produto ANVISA {ap.registro}",
                    "linha": ap.fabricante,
                    "descricao_tecnica": ap.nome_tecnico or "",
                    "diferenciais_clinicos": (ap.modelos_descricao or "")[:200],
                    "codigo_tuss_sugerido": "",
                    "registro_anvisa": ap.registro,
                    "classe_risco": ap.classe_risco,
                    "source": "anvisa",
                })

    return {"items": items}


@router.post("")
async def create_product_quick(
    body: QuickProductIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cadastro rápido de produto OPME (campos mínimos)."""
    # TODO: re-enable auth when ready
    product = Product(
        nome=body.nome,
        linha=body.fabricante,
        registro_anvisa=body.registro_anvisa,
        codigo_tuss_sugerido=body.codigo_tuss_sugerido,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)
    await db.commit()
    return {
        "id": str(product.id),
        "nome": product.nome,
        "linha": product.linha,
        "registro_anvisa": product.registro_anvisa,
        "codigo_tuss_sugerido": product.codigo_tuss_sugerido,
    }


@router.post("/from-anvisa/{registro}")
async def create_from_anvisa(
    registro: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cria produto no catálogo a partir de um registro ANVISA existente."""
    # TODO: re-enable auth when ready

    # Verifica se já existe no catálogo
    existing = await db.execute(
        select(Product).where(Product.registro_anvisa == registro)
    )
    if existing.scalar_one_or_none():
        p = existing.scalar_one_or_none()
        # Already done above, re-query
        result = await db.execute(
            select(Product).where(Product.registro_anvisa == registro)
        )
        p = result.scalar_one_or_none()
        return {
            "id": str(p.id),
            "nome": p.nome,
            "linha": p.linha,
            "registro_anvisa": p.registro_anvisa,
            "codigo_tuss_sugerido": p.codigo_tuss_sugerido,
            "already_exists": True,
        }

    # Busca na base ANVISA
    anvisa_result = await db.execute(
        select(AnvisaProduct).where(AnvisaProduct.registro == registro)
    )
    ap = anvisa_result.scalar_one_or_none()
    if not ap:
        raise HTTPException(status_code=404, detail="Registro ANVISA não encontrado")

    # Cria produto no catálogo com dados técnicos da ANVISA
    product = Product(
        nome=ap.nome_comercial or f"Produto ANVISA {ap.registro}",
        linha=ap.fabricante,
        registro_anvisa=ap.registro,
        descricao_tecnica=ap.nome_tecnico,
        indicacoes=ap.modelos_descricao,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)
    await db.commit()

    return {
        "id": str(product.id),
        "nome": product.nome,
        "linha": product.linha,
        "registro_anvisa": product.registro_anvisa,
        "codigo_tuss_sugerido": product.codigo_tuss_sugerido,
        "classe_risco": ap.classe_risco,
        "already_exists": False,
    }


@router.get("/{product_id}")
async def get_product(
    product_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Detalhes completos de um produto (verdades absolutas)."""
    # TODO: re-enable auth when ready
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
