"""
Agente A: O Pesquisador (The Researcher).
Busca evidências científicas e identifica lacunas que exigem input do médico.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ClinicalEvidence
from .prompts import RESEARCHER_SYSTEM
from .token_tracker import TokenUsage, extract_usage

__all__ = [
    "research", "ResearchResult", "GapQuestion", "Evidence",
    "_fetch_clinical_evidences", "_fetch_pubmed_evidences",
]

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    texto: str
    referencia: str
    relevancia: str = "media"


@dataclass
class GapQuestion:
    secao: str
    pergunta: str
    opcoes: list[dict] = field(default_factory=list)
    prioridade: str = "critica"  # critica | fortalecimento


# Lacunas sem as quais o relatório é glosado
CRITICAL_GAPS = {"falha_terapeutica", "risco_nao_realizacao", "diagnostico"}
# Lacunas que fortalecem mas não são obrigatórias
STRENGTHENING_GAPS = {"citacao_recente", "estudo_adicional", "dado_complementar"}


@dataclass
class ResearchResult:
    evidencias: list[Evidence] = field(default_factory=list)
    referencias: list[str] = field(default_factory=list)
    lacunas: list[GapQuestion] = field(default_factory=list)
    dicas_ia: list[dict] = field(default_factory=list)
    sugestao_tuss: Optional[str] = None
    especialidade_detectada: Optional[str] = None
    raw_response: Optional[str] = None
    token_usage: Optional[TokenUsage] = None


def _build_product_context(product) -> str:
    parts = [f"Nome: {product.nome}"]
    if product.linha:
        parts.append(f"Linha: {product.linha}")
    if product.descricao_tecnica:
        parts.append(f"Descrição técnica: {product.descricao_tecnica}")
    if product.diferenciais_clinicos:
        parts.append(f"Diferenciais clínicos: {product.diferenciais_clinicos}")
    if product.indicacoes:
        parts.append(f"Indicações: {product.indicacoes}")
    if product.viscosidade:
        parts.append(f"Viscosidade: {product.viscosidade}")
    if product.peso_molecular:
        parts.append(f"Peso molecular: {product.peso_molecular}")
    if product.concentracao:
        parts.append(f"Concentração: {product.concentracao}")
    if product.registro_anvisa:
        parts.append(f"Registro ANVISA: {product.registro_anvisa}")
    if product.referencias_bibliograficas:
        parts.append(f"Referências conhecidas: {', '.join(product.referencias_bibliograficas)}")
    return "\n".join(parts)


async def _fetch_clinical_evidences(db: Optional[AsyncSession], cid: str, product_id) -> list[dict]:
    """Busca evidências pré-validadas no banco por CID + produto."""
    if not db or not cid:
        return []
    try:
        stmt = select(ClinicalEvidence).where(
            ClinicalEvidence.cid == cid.strip().upper(),
            ClinicalEvidence.product_id == product_id,
        ).order_by(ClinicalEvidence.relevancia)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "snippet": r.snippet,
                "autor": r.autor,
                "referencia_completa": r.referencia_completa or f"{r.autor} ({r.ano})",
                "ano": r.ano,
                "tipo": r.tipo,
                "doi": getattr(r, "doi", ""),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("Falha ao buscar clinical_evidences: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return []


async def _fetch_pubmed_evidences(db: Optional[AsyncSession], cid: str, product_name: str, diagnostico: str) -> list[dict]:
    """Busca evidências do PubMed (cache progressivo)."""
    if not db or not cid:
        return []
    try:
        from app.services.pubmed_service import get_evidences_for_cid
        return await get_evidences_for_cid(db, cid, product_name, diagnostico)
    except Exception as e:
        logger.warning("Falha ao buscar PubMed evidences: %s", e)
        try:
            await db.rollback()
        except Exception:
            pass
        return []


async def research(product, diagnostico: str, cid: str, template=None, db: Optional[AsyncSession] = None) -> ResearchResult:
    """
    Executa pesquisa sobre a patologia e o produto.
    Retorna evidências, referências e lacunas que precisam de input do médico.
    """
    product_context = _build_product_context(product)

    db_evidences = await _fetch_clinical_evidences(db, cid, product.id)
    pubmed_evidences = await _fetch_pubmed_evidences(db, cid, product.nome, diagnostico)

    # Knowledge Graph context (Tier 1-3)
    graph_context = ""
    try:
        from app.services.knowledge_graph import query_knowledge_graph, format_graph_context_for_llm
        if db:
            ctx = await query_knowledge_graph(db, cid, str(product.id), max_depth=3)
            graph_context = format_graph_context_for_llm(ctx)
            if graph_context:
                logger.info("Graph context injected: %d chars", len(graph_context))
    except Exception as e:
        logger.debug("Knowledge graph context skipped: %s", e)

    system_prompt = RESEARCHER_SYSTEM.format(product_context=product_context)

    user_message = (
        f"Patologia/Diagnóstico: {diagnostico}\n"
        f"CID: {cid}\n"
        f"Material OPME solicitado: {product.nome}\n"
    )

    if graph_context:
        user_message += f"\n{graph_context}\n"

    if db_evidences:
        user_message += "\n--- EVIDÊNCIAS INTERNAS PRÉ-VALIDADAS (VERIFICADAS) ---\n"
        user_message += "USE ESTAS EVIDÊNCIAS OBRIGATORIAMENTE no relatório. São dados verificados.\n\n"
        for i, ev in enumerate(db_evidences, 1):
            user_message += (
                f"[Evidência Interna {i}] ({ev['tipo'] or 'estudo'})\n"
                f"  Autor: {ev['autor']}\n"
                f"  Ano: {ev['ano']}\n"
                f"  Snippet: {ev['snippet']}\n"
                f"  Referência: {ev['referencia_completa']}\n\n"
            )

    if pubmed_evidences:
        user_message += "\n--- EVIDÊNCIAS PUBMED (artigos científicos indexados) ---\n"
        user_message += "Use estas evidências para ENRIQUECER o relatório com referências adicionais.\n\n"
        offset = len(db_evidences)
        for i, ev in enumerate(pubmed_evidences[:10], 1):
            user_message += (
                f"[PubMed {offset + i}] ({ev.get('tipo', 'article')}) PMID: {ev.get('pmid', '')}\n"
                f"  Autor: {ev['autor']}\n"
                f"  Ano: {ev['ano']}\n"
                f"  Journal: {ev.get('journal', '')}\n"
                f"  Resumo: {ev['snippet'][:300]}\n"
                f"  Referência: {ev.get('referencia_completa', '')}\n\n"
            )

    if template:
        user_message += f"\nTemplate de referência disponível: {template.nome}\n"
        if template.referencias_padrao:
            user_message += f"Referências padrão do template: {json.dumps(template.referencias_padrao)}\n"

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        model = settings.OPENAI_MODEL_RESEARCHER
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=3000,
        )

        raw = response.choices[0].message.content
        usage = extract_usage(response, "Pesquisador", model=model)
        data = json.loads(raw)

        all_lacunas = []
        for l in data.get("lacunas", []):
            secao = l.get("secao", "")
            prioridade = l.get("prioridade", "critica" if secao in CRITICAL_GAPS else "fortalecimento")
            all_lacunas.append(GapQuestion(
                secao=secao,
                pergunta=l.get("pergunta", ""),
                opcoes=l.get("opcoes", []),
                prioridade=prioridade,
            ))

        critical_lacunas = [l for l in all_lacunas if l.prioridade == "critica"]
        strengthening_lacunas = [l for l in all_lacunas if l.prioridade == "fortalecimento"]

        dicas_ia = data.get("dicas_ia", [])
        for sl in strengthening_lacunas:
            dicas_ia.append({"tipo": "sugestao", "texto": sl.pergunta})

        return ResearchResult(
            evidencias=[
                Evidence(
                    texto=e.get("texto", ""),
                    referencia=e.get("referencia", ""),
                    relevancia=e.get("relevancia", "media"),
                )
                for e in data.get("evidencias", [])
            ],
            referencias=data.get("referencias_bibliograficas", []),
            lacunas=critical_lacunas,
            dicas_ia=dicas_ia,
            sugestao_tuss=data.get("sugestao_tuss"),
            especialidade_detectada=data.get("especialidade_detectada"),
            raw_response=raw,
            token_usage=usage,
        )

    except Exception as e:
        logger.exception("Agente Pesquisador falhou: %s", e)
        return ResearchResult(
            lacunas=[
                GapQuestion(
                    secao="falha_terapeutica",
                    pergunta="Quais tratamentos anteriores foram tentados sem sucesso?",
                    opcoes=[
                        {"id": "A", "texto": "Tratamento medicamentoso sem melhora"},
                        {"id": "B", "texto": "Fisioterapia sem ganho funcional"},
                        {"id": "C", "texto": "Procedimento anterior com complicações"},
                    ],
                ),
                GapQuestion(
                    secao="risco_nao_realizacao",
                    pergunta="Qual o principal risco caso o procedimento não seja realizado?",
                    opcoes=[
                        {"id": "A", "texto": "Progressão da doença com perda funcional"},
                        {"id": "B", "texto": "Dor crônica intratável"},
                        {"id": "C", "texto": "Risco de complicações graves"},
                    ],
                ),
            ],
            raw_response=str(e),
        )
