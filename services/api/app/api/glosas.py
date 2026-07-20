"""Endpoints de inteligência de glosa (Painel ANS + TISS Tabela 38).

Somente leitura; dados carregados pelos ETLs
scripts/etl/download_glosa_panel.py e scripts/etl/ingest_tabela38.py.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.glosa_service import (
    build_glosa_alert,
    get_glosa_motivo,
    get_operadora_glosa_summary,
    search_operadoras,
)

router = APIRouter()


@router.get("/operadora")
async def operadora_glosa(
    nome: str = Query(..., min_length=2, description="Nome do convênio como digitado pelo médico"),
    db: AsyncSession = Depends(get_db),
):
    """Indicadores de glosa da operadora (fuzzy match + resumo dos últimos 12 meses)."""
    summary = await get_operadora_glosa_summary(db, nome)
    if not summary:
        return {"found": False, "nome": nome}
    return {"found": True, **summary.to_dict(), "alerta": build_glosa_alert(summary)}


@router.get("/operadoras")
async def operadoras_autocomplete(
    q: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
):
    """Autocomplete de operadoras (para a UI substituir o input livre de convênio)."""
    return {"items": await search_operadoras(db, q)}


@router.get("/motivos/{codigo}")
async def glosa_motivo(codigo: str, db: AsyncSession = Depends(get_db)):
    """Consulta um motivo de glosa oficial da TISS Tabela 38."""
    motivo = await get_glosa_motivo(db, codigo)
    if not motivo:
        return {"found": False, "codigo": codigo}
    return {
        "found": True,
        "codigo": motivo.codigo,
        "descricao": motivo.descricao,
        "ativo": motivo.ativo,
        "vigencia_fim": motivo.vigencia_fim.date().isoformat() if motivo.vigencia_fim else None,
        "versao_tiss": motivo.versao_tiss,
    }
