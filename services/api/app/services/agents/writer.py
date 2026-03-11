"""
Agente B: O Redator (The Writer).
Consolida pesquisa + inputs do médico + template DNA em justificativa formal.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from .prompts import WRITER_SYSTEM
from .researcher import ResearchResult
from .token_tracker import TokenUsage, extract_usage

logger = logging.getLogger(__name__)


@dataclass
class DraftReport:
    justificativa_completa: str = ""
    diagnostico_resumo: str = ""
    falha_terapeutica: str = ""
    risco_nao_realizacao: str = ""
    base_legal: str = ""
    referencias: list[str] = field(default_factory=list)
    raw_response: Optional[str] = None
    token_usage: Optional[TokenUsage] = None


def _build_product_facts(product) -> str:
    facts = []
    facts.append(f"Nome: {product.nome}")
    if product.linha:
        facts.append(f"Linha: {product.linha}")
    if product.viscosidade:
        facts.append(f"Viscosidade (OFICIAL): {product.viscosidade}")
    if product.peso_molecular:
        facts.append(f"Peso molecular (OFICIAL): {product.peso_molecular}")
    if product.concentracao:
        facts.append(f"Concentração (OFICIAL): {product.concentracao}")
    if product.registro_anvisa:
        facts.append(f"Registro ANVISA: {product.registro_anvisa}")
    if product.diferenciais_clinicos:
        facts.append(f"Diferenciais clínicos: {product.diferenciais_clinicos}")
    return "\n".join(facts)


def _build_template_context(template) -> str:
    if not template:
        return "Nenhum template disponível. Use tom científico formal."
    parts = []
    if template.tom_de_voz:
        parts.append(f"Tom de voz: {template.tom_de_voz}")
    if template.template_corpo:
        parts.append(f"Modelo de referência:\n{template.template_corpo}")
    if template.bases_legais:
        parts.append(f"Bases legais: {json.dumps(template.bases_legais)}")
    exemplos = getattr(template, 'exemplos_aprovados', None)
    if exemplos:
        ranked = sorted(exemplos, key=len, reverse=True)[:3]
        parts.append("\nEXEMPLOS DE RELATÓRIOS JÁ APROVADOS POR CONVÊNIOS (copie este estilo EXATAMENTE):")
        for i, ex in enumerate(ranked, 1):
            parts.append(f"--- Exemplo Aprovado {i} ---\n{ex}")
    return "\n".join(parts) or "Tom científico formal."


async def write_justification(
    research: ResearchResult,
    product,
    template,
    medico_inputs: dict,
    clinical_evidences: list[dict] | None = None,
    pubmed_evidences: list[dict] | None = None,
) -> DraftReport:
    """
    Redige a justificativa técnica com base na pesquisa, produto e inputs do médico.
    """
    product_facts = _build_product_facts(product)
    template_context = _build_template_context(template)

    evidence_parts = []

    if clinical_evidences:
        evidence_parts.append("=== EVIDÊNCIAS INTERNAS VERIFICADAS (use OBRIGATORIAMENTE, cite AUTOR e ANO) ===")
        for i, ev in enumerate(clinical_evidences, 1):
            evidence_parts.append(
                f"[Interna {i}] Autor: {ev['autor']} | Ano: {ev['ano']} | Tipo: {ev.get('tipo', 'estudo')}\n"
                f"    Snippet: {ev['snippet']}\n"
                f"    Citação: ({ev['autor']} et al., {ev['ano']})"
            )

    if pubmed_evidences:
        evidence_parts.append("\n=== EVIDÊNCIAS PUBMED (cite AUTOR, ANO e PMID) ===")
        offset = len(clinical_evidences or [])
        for i, ev in enumerate(pubmed_evidences[:10], 1):
            evidence_parts.append(
                f"[PubMed {offset + i}] Autor: {ev['autor']} | Ano: {ev['ano']} | "
                f"PMID: {ev.get('pmid', '')} | Tipo: {ev.get('tipo', 'article')}\n"
                f"    Journal: {ev.get('journal', '')}\n"
                f"    Resumo: {ev['snippet'][:300]}\n"
                f"    Referência completa: {ev.get('referencia_completa', '')}\n"
                f"    Citação: ({ev['autor']} et al., {ev['ano']})"
            )

    researcher_evidence = "\n".join(
        f"- {e.texto} (Ref: {e.referencia})" for e in research.evidencias
    )
    if researcher_evidence:
        evidence_parts.append("\n=== EVIDÊNCIAS DO PESQUISADOR ===")
        evidence_parts.append(researcher_evidence)

    evidence_text = "\n".join(evidence_parts) or "Nenhuma evidência adicional encontrada pelo pesquisador."

    medico_text = "\n".join(
        f"- {k}: {v}" for k, v in medico_inputs.items() if v
    )

    system_prompt = WRITER_SYSTEM.format(
        template_context=template_context,
        product_facts=product_facts,
        research_evidence=evidence_text,
        medico_inputs=medico_text,
    )

    user_message = (
        f"Diagnóstico: {medico_inputs.get('diagnostico', '')}\n"
        f"CID: {medico_inputs.get('cid', '')}\n"
        f"Procedimento: {medico_inputs.get('surgery_description', '')}\n"
        f"Material: {product.nome}\n"
    )

    if medico_inputs.get("falha_terapeutica"):
        user_message += f"Falha terapêutica prévia: {medico_inputs['falha_terapeutica']}\n"
    if medico_inputs.get("risco_nao_realizacao"):
        user_message += f"Risco da não realização: {medico_inputs['risco_nao_realizacao']}\n"

    try:
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=4000,
        )

        raw = response.choices[0].message.content
        usage = extract_usage(response, "Redator")
        data = json.loads(raw)

        return DraftReport(
            justificativa_completa=data.get("justificativa_completa", ""),
            diagnostico_resumo=data.get("diagnostico_resumo", ""),
            falha_terapeutica=data.get("falha_terapeutica", ""),
            risco_nao_realizacao=data.get("risco_nao_realizacao", ""),
            base_legal=data.get("base_legal", ""),
            referencias=data.get("referencias", []),
            raw_response=raw,
            token_usage=usage,
        )

    except Exception as e:
        logger.exception("Agente Redator falhou: %s", e)
        base_legal = (
            "Conforme a RN 395 da ANS, em caso de divergência quanto à indicação do material, "
            "a operadora deverá apresentar justificativa técnica por escrito, fundamentada em evidências científicas."
        )
        return DraftReport(
            justificativa_completa=(
                f"Paciente com diagnóstico de {medico_inputs.get('diagnostico', '[diagnóstico]')} "
                f"(CID {medico_inputs.get('cid', '[CID]')}), para o qual se faz necessária a utilização "
                f"de {product.nome}. {product.diferenciais_clinicos or ''} {base_legal}"
            ),
            diagnostico_resumo=medico_inputs.get("diagnostico", ""),
            base_legal=base_legal,
            raw_response=str(e),
        )
