"""API de Produtos OPME — busca em catálogo interno + base ANVISA (96k+ registros)."""
import logging
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from sqlalchemy import text as sql_text

from app.db.session import get_db, AsyncSessionLocal
from app.db.models import Product, AnvisaProduct, ProductTussMapping, TussMaterial
from app.core.security import get_current_user_id, require_current_user_id
from app.services.ifu_enrichment import enrich_product_from_ifu

logger = logging.getLogger(__name__)

router = APIRouter()


class QuickProductIn(BaseModel):
    nome: str
    registro_anvisa: Optional[str] = None
    fabricante: Optional[str] = None
    codigo_tuss_sugerido: Optional[str] = None


@router.get("")
async def list_products(
    q: Optional[str] = Query(None, description="Busca por nome ou linha"),
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Lista produtos: primeiro catálogo interno, depois base ANVISA."""

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
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cadastro rápido de produto OPME (campos mínimos)."""
    product = Product(
        nome=body.nome,
        linha=body.fabricante,
        registro_anvisa=body.registro_anvisa,
        codigo_tuss_sugerido=body.codigo_tuss_sugerido,
    )
    db.add(product)
    await db.flush()
    await db.refresh(product)

    # Mapeamento automático TUSS se tem registro ANVISA
    tuss_codes_mapped = []
    if body.registro_anvisa:
        tuss_result = await db.execute(
            select(TussMaterial).where(
                TussMaterial.registro_anvisa == body.registro_anvisa,
                TussMaterial.ativo == True,
            )
        )
        tuss_matches = tuss_result.scalars().all()

        for i, tm in enumerate(tuss_matches):
            mapping = ProductTussMapping(
                product_id=product.id,
                tuss_code=tm.codigo_tuss,
                procedure_name=tm.nome,
                subgroup=tm.subgrupo,
                is_primary=(i == 0),
            )
            db.add(mapping)
            tuss_codes_mapped.append({
                "tuss_code": tm.codigo_tuss,
                "nome": tm.nome,
            })

        if tuss_matches and not body.codigo_tuss_sugerido:
            product.codigo_tuss_sugerido = tuss_matches[0].codigo_tuss

    await db.commit()
    await db.refresh(product)
    return {
        "id": str(product.id),
        "nome": product.nome,
        "linha": product.linha,
        "registro_anvisa": product.registro_anvisa,
        "codigo_tuss_sugerido": product.codigo_tuss_sugerido,
        "tuss_mappings": tuss_codes_mapped,
    }


async def _background_ifu_enrich(product_id: str):
    """Background task: enrich product from manufacturer IFU PDF."""
    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Product).where(Product.id == product_id)
            )
            product = result.scalar_one_or_none()
            if product:
                enriched = await enrich_product_from_ifu(db, product)
                if enriched:
                    logger.info(
                        "IFU enrichment OK para %s: %s",
                        product.nome, list(enriched.keys())
                    )
                else:
                    logger.info("IFU não encontrado para %s", product.nome)
    except Exception as e:
        logger.warning("Background IFU enrichment falhou: %s", e)


# ============================================================================
# ANVISA API Gateway — Consulta e Validação em tempo real
# ============================================================================

@router.get("/anvisa/consulta/{registro}")
async def consultar_anvisa(
    registro: str,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Consulta registro ANVISA via API Gateway (OAuth2) com fallback para banco local.
    Retorna dados do produto, status e fonte da informação.
    """
    from app.services.anvisa_service import consultar_registro
    result = await consultar_registro(db, registro)
    await db.commit()
    return {
        "registro": result.registro,
        "nome_comercial": result.nome_comercial,
        "nome_tecnico": result.nome_tecnico,
        "fabricante": result.fabricante,
        "classe_risco": result.classe_risco,
        "status": result.status,
        "data_validade": result.data_validade.isoformat() if result.data_validade else None,
        "fonte": result.fonte,
        "sucesso": result.sucesso,
    }


@router.get("/anvisa/validar/{registro}")
async def validar_anvisa(
    registro: str,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Valida se registro ANVISA está ativo (STF Critério 5 - ADI 7.265).
    Retorna status de validade e motivo se inválido.
    """
    from app.services.anvisa_service import validar_registro_ativo
    result = await validar_registro_ativo(db, registro)
    await db.commit()
    return result


@router.post("/from-anvisa/{registro}")
async def create_from_anvisa(
    registro: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Cria produto no catálogo a partir de um registro ANVISA existente."""

    # Verifica se já existe no catálogo
    existing = await db.execute(
        select(Product).where(Product.registro_anvisa == registro)
    )
    p = existing.scalar_one_or_none()
    if p:
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

    # 🔗 Mapeamento automático TUSS via registro_anvisa
    tuss_result = await db.execute(
        select(TussMaterial).where(
            TussMaterial.registro_anvisa == registro,
            TussMaterial.ativo == True,
        )
    )
    tuss_matches = tuss_result.scalars().all()

    tuss_codes_mapped = []
    for i, tm in enumerate(tuss_matches):
        mapping = ProductTussMapping(
            product_id=product.id,
            tuss_code=tm.codigo_tuss,
            procedure_name=tm.nome,
            subgroup=tm.subgrupo,
            is_primary=(i == 0),
        )
        db.add(mapping)
        tuss_codes_mapped.append({
            "tuss_code": tm.codigo_tuss,
            "nome": tm.nome,
            "is_primary": (i == 0),
        })

    # Define o primeiro código TUSS como sugerido no produto
    if tuss_matches:
        product.codigo_tuss_sugerido = tuss_matches[0].codigo_tuss

    await db.commit()
    await db.refresh(product)

    # Background: enriquecer com dados da instrução de uso do fabricante (zero custo)
    background_tasks.add_task(_background_ifu_enrich, str(product.id))

    return {
        "id": str(product.id),
        "nome": product.nome,
        "linha": product.linha,
        "registro_anvisa": product.registro_anvisa,
        "codigo_tuss_sugerido": product.codigo_tuss_sugerido,
        "classe_risco": ap.classe_risco,
        "already_exists": False,
        "tuss_mappings": tuss_codes_mapped,
    }


@router.post("/{product_id}/enrich")
async def enrich_product_endpoint(
    product_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Enriquece produto com dados da instrução de uso do fabricante (zero custo IA)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    enriched = await enrich_product_from_ifu(db, product)

    if not enriched:
        return {
            "status": "not_found",
            "message": "Instrução de uso não encontrada para este produto",
        }

    return {
        "status": "enriched",
        "fields_updated": [k for k in enriched.keys()],
        "bula_url": enriched.get("bula_url"),
        "indicacoes_preview": (enriched.get("indicacoes") or "")[:200],
        "contraindicacoes_preview": (enriched.get("contraindicacoes") or "")[:200],
    }


@router.get("/{product_id}")
async def get_product(
    product_id: UUID,
    user_id: str = Depends(require_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Detalhes completos de um produto (verdades absolutas)."""
    result = await db.execute(select(Product).where(Product.id == product_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Product not found")

    tuss_result = await db.execute(
        select(ProductTussMapping).where(ProductTussMapping.product_id == p.id)
    )
    tuss_mappings = [
        {
            "tuss_code": m.tuss_code,
            "procedure_name": m.procedure_name,
            "subgroup": m.subgroup,
            "is_primary": m.is_primary,
        }
        for m in tuss_result.scalars().all()
    ]

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
        "tuss_mappings": tuss_mappings,
    }
