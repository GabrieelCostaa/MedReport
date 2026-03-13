"""
Seleção determinística do código TUSS correto para um produto + diagnóstico.

Cada produto OPME pode ser usado em dezenas de procedimentos diferentes.
O código TUSS correto depende do diagnóstico/CID do paciente, não só do produto.
Esta seleção é zero-LLM: keyword matching puro.
"""
import re
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProductTussMapping

logger = logging.getLogger(__name__)


@dataclass
class TussSelection:
    tuss_code: str
    procedure_name: str
    confidence: str  # "exact" | "keyword" | "primary" | "fallback"
    reason: str


def _normalize(text: str) -> set[str]:
    """Extrai palavras-chave normalizadas (>= 4 chars) de um texto."""
    text = text.lower()
    text = re.sub(r"[áàãâä]", "a", text)
    text = re.sub(r"[éèêë]", "e", text)
    text = re.sub(r"[íìîï]", "i", text)
    text = re.sub(r"[óòõôö]", "o", text)
    text = re.sub(r"[úùûü]", "u", text)
    text = re.sub(r"[ç]", "c", text)
    words = re.findall(r"[a-z]{4,}", text)
    # Remove stop words
    stops = {"para", "como", "pela", "pelo", "pelas", "pelos", "mais", "menos",
             "cada", "entre", "sobre", "desde", "este", "esta", "esse", "essa",
             "aquele", "aquela", "tratamento", "cirurgico", "cirurgica", "tecnica"}
    return {w for w in words if w not in stops}


def _score_mapping(mapping: ProductTussMapping, query_keywords: set[str]) -> float:
    """Pontua um mapeamento pela sobreposição de palavras-chave."""
    mapping_text = f"{mapping.procedure_name or ''} {mapping.applications or ''} {mapping.subgroup or ''}"
    mapping_kw = _normalize(mapping_text)
    if not mapping_kw or not query_keywords:
        return 0.0
    overlap = mapping_kw & query_keywords
    # Jaccard-like score weighted by overlap size
    return len(overlap) / min(len(mapping_kw), len(query_keywords)) if overlap else 0.0


async def select_best_tuss(
    db: AsyncSession,
    product_id,
    cid: str = "",
    diagnosis: str = "",
    product_fallback_tuss: str = "",
) -> TussSelection:
    """
    Seleciona o melhor código TUSS para um produto + contexto clínico.

    Algoritmo (determinístico, zero LLM):
    1. Busca todos os mapeamentos do produto
    2. Se só há um, retorna direto
    3. Pontua cada mapeamento por keyword overlap com diagnóstico/CID
    4. Se há match claro, retorna com confidence "keyword"
    5. Senão, retorna o is_primary=True com confidence "primary"
    6. Se não há mapeamentos, fallback para codigo_tuss_sugerido
    """
    result = await db.execute(
        select(ProductTussMapping).where(
            ProductTussMapping.product_id == str(product_id)
        )
    )
    mappings = result.scalars().all()

    if not mappings:
        # Sem mapeamentos — fallback para campo legado
        if product_fallback_tuss:
            return TussSelection(
                tuss_code=product_fallback_tuss,
                procedure_name="",
                confidence="fallback",
                reason="Nenhum mapeamento TUSS encontrado — usando código legado do produto",
            )
        return TussSelection(
            tuss_code="",
            procedure_name="",
            confidence="fallback",
            reason="Produto sem código TUSS",
        )

    if len(mappings) == 1:
        m = mappings[0]
        return TussSelection(
            tuss_code=m.tuss_code,
            procedure_name=m.procedure_name,
            confidence="exact",
            reason="Único mapeamento TUSS para este produto",
        )

    # Construir query keywords a partir do diagnóstico + CID
    query_text = f"{cid} {diagnosis}"
    query_kw = _normalize(query_text)

    if not query_kw:
        # Sem contexto para matching — retornar o primário
        primary = next((m for m in mappings if m.is_primary), mappings[0])
        return TussSelection(
            tuss_code=primary.tuss_code,
            procedure_name=primary.procedure_name,
            confidence="primary",
            reason=f"Código primário do produto ({len(mappings)} mapeamentos disponíveis)",
        )

    # Pontuar cada mapeamento
    scored = [(m, _score_mapping(m, query_kw)) for m in mappings]
    scored.sort(key=lambda x: (-x[1], not x[0].is_primary))

    best_mapping, best_score = scored[0]

    if best_score >= 0.3:
        return TussSelection(
            tuss_code=best_mapping.tuss_code,
            procedure_name=best_mapping.procedure_name,
            confidence="keyword",
            reason=f"Match por keywords (score={best_score:.2f}, {len(mappings)} mapeamentos)",
        )

    # Score baixo — usar primário
    primary = next((m for m in mappings if m.is_primary), mappings[0])
    return TussSelection(
        tuss_code=primary.tuss_code,
        procedure_name=primary.procedure_name,
        confidence="primary",
        reason=f"Sem match forte com diagnóstico — usando código primário ({len(mappings)} mapeamentos)",
    )
