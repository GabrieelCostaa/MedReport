"""
Agente B: O Redator (The Writer).
Consolida pesquisa + inputs do médico + template DNA em justificativa formal.

Usa Instructor (structured outputs) para garantir schema JSON válido via Pydantic.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import settings
from .prompts import WRITER_SYSTEM
from .researcher import ResearchResult
from .token_tracker import TokenUsage, extract_usage
from .schemas import WriterOutput
from .few_shot_examples import get_few_shot_messages

try:
    import instructor
    INSTRUCTOR_AVAILABLE = True
except ImportError:
    instructor = None
    INSTRUCTOR_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class DraftReport:
    justificativa_completa: str = ""
    diagnostico_resumo: str = ""
    quadro_clinico: str = ""
    falha_terapeutica: str = ""
    justificativa_tecnica: str = ""
    evidencia_cientifica: str = ""
    risco_nao_realizacao: str = ""
    conclusao: str = ""
    base_legal: str = ""
    referencias: list[str] = field(default_factory=list)
    raw_response: Optional[str] = None
    token_usage: Optional[TokenUsage] = None


# Títulos das seções na montagem do corpo (justificativa_completa).
_SECTION_TITLES = [
    ("quadro_clinico", "QUADRO CLÍNICO E HISTÓRIA"),
    ("falha_terapeutica", "FALHA TERAPÊUTICA PRÉVIA"),
    ("justificativa_tecnica", "JUSTIFICATIVA TÉCNICA E SUPERIORIDADE DO MATERIAL"),
    ("evidencia_cientifica", "EVIDÊNCIA CIENTÍFICA"),
    ("risco_nao_realizacao", "RISCO DA NÃO REALIZAÇÃO"),
    ("conclusao", "CONCLUSÃO"),
]


def _assemble_body(sections: dict) -> str:
    """Monta o corpo da justificativa a partir das seções, com títulos.

    Não regera nada — apenas concatena o que o Redator já produziu, de forma
    determinística, mantendo compatível o campo único `justificativa_completa`.
    """
    parts = []
    for key, titulo in _SECTION_TITLES:
        conteudo = (sections.get(key) or "").strip()
        if conteudo:
            parts.append(f"{titulo}\n{conteudo}")
    return "\n\n".join(parts)


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
    if getattr(product, "codigo_tuss_sugerido", None):
        facts.append(f"Código TUSS: {product.codigo_tuss_sugerido}")
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
        parts.append("\nEXEMPLOS DE RELATÓRIOS JÁ APROVADOS POR CONVÊNIOS (inspire-se no estilo, tom, estrutura e PROFUNDIDADE — não limite o tamanho ao do exemplo):")
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
        n_pubmed = min(len(pubmed_evidences), 10)
        evidence_parts.append(
            f"\n=== EVIDÊNCIAS PUBMED — {n_pubmed} artigos (VOCÊ DEVE citar TODOS no texto) ==="
        )
        offset = len(clinical_evidences or [])
        for i, ev in enumerate(pubmed_evidences[:10], 1):
            evidence_parts.append(
                f"[PubMed {offset + i}] Autor: {ev['autor']} | Ano: {ev['ano']} | "
                f"PMID: {ev.get('pmid', '')} | Tipo: {ev.get('tipo', 'article')}\n"
                f"    Journal: {ev.get('journal', '')}\n"
                f"    Resumo: {ev['snippet'][:500]}\n"
                f"    Referência completa: {ev.get('referencia_completa', '')}\n"
                f"    Citação: ({ev['autor']} et al., {ev['ano']})"
            )
        evidence_parts.append(
            f"\n⚠️ ATENÇÃO: Você recebeu {n_pubmed} evidências PubMed acima. "
            f"CADA UMA deve ser citada pelo menos 1x no texto com (Autor et al., Ano). "
            f"Se você não citar todas, o relatório será REPROVADO na auditoria."
        )

    researcher_evidence = "\n".join(
        f"- {e.texto} (Ref: {e.referencia})" for e in research.evidencias
    )
    if researcher_evidence:
        evidence_parts.append("\n=== EVIDÊNCIAS DO PESQUISADOR ===")
        evidence_parts.append(researcher_evidence)

    evidence_text = "\n".join(evidence_parts) or "Nenhuma evidência adicional encontrada pelo pesquisador."

    # Chaves com "_" são internas (ex.: _trace do observability) — não entram no prompt.
    medico_text = "\n".join(
        f"- {k}: {v}" for k, v in medico_inputs.items() if v and not k.startswith("_")
    )

    system_prompt = WRITER_SYSTEM.format(
        template_context=template_context,
        product_facts=product_facts,
        research_evidence=evidence_text,
        medico_inputs=medico_text,
    )

    tuss_code = getattr(product, "codigo_tuss_sugerido", "") or ""
    user_message = (
        f"Diagnóstico: {medico_inputs.get('diagnostico', '')}\n"
        f"CID: {medico_inputs.get('cid', '')}\n"
        f"Procedimento: {medico_inputs.get('surgery_description', '')}\n"
        f"Material: {product.nome}\n"
        f"Código TUSS: {tuss_code or 'não informado'}\n"
    )

    if medico_inputs.get("falha_terapeutica"):
        user_message += f"Falha terapêutica prévia: {medico_inputs['falha_terapeutica']}\n"
    if medico_inputs.get("risco_nao_realizacao"):
        user_message += f"Risco da não realização: {medico_inputs['risco_nao_realizacao']}\n"

    try:
        import openai

        # Build messages with optional few-shot examples per specialty
        especialidade = medico_inputs.get("especialidade", "") or ""
        messages = [{"role": "system", "content": system_prompt}]
        few_shot = get_few_shot_messages(especialidade)
        messages.extend(few_shot)
        messages.append({"role": "user", "content": user_message})

        model = settings.OPENAI_MODEL_WRITER

        if INSTRUCTOR_AVAILABLE:
            # Instructor: forces Pydantic schema, auto-retries on validation errors.
            # create_with_completion também retorna a completion crua p/ capturar usage.
            async_client = instructor.from_openai(
                openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            )
            result, completion = await async_client.chat.completions.create_with_completion(
                model=model,
                response_model=WriterOutput,
                messages=messages,
                temperature=0.2,
                max_tokens=8000,
                max_retries=2,
            )
            usage = extract_usage(completion, "Redator", model=model)
            sections = {
                "quadro_clinico": result.quadro_clinico,
                "falha_terapeutica": result.falha_terapeutica,
                "justificativa_tecnica": result.justificativa_tecnica,
                "evidencia_cientifica": result.evidencia_cientifica,
                "risco_nao_realizacao": result.risco_nao_realizacao,
                "conclusao": result.conclusao,
            }
            return DraftReport(
                justificativa_completa=_assemble_body(sections),
                diagnostico_resumo=result.diagnostico_resumo,
                quadro_clinico=result.quadro_clinico,
                falha_terapeutica=result.falha_terapeutica,
                justificativa_tecnica=result.justificativa_tecnica,
                evidencia_cientifica=result.evidencia_cientifica,
                risco_nao_realizacao=result.risco_nao_realizacao,
                conclusao=result.conclusao,
                base_legal=result.base_legal,
                referencias=result.referencias,
                raw_response=result.model_dump_json(),
                token_usage=usage,
            )
        else:
            # Fallback: raw JSON mode
            client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=8000,
            )
            raw = response.choices[0].message.content
            usage = extract_usage(response, "Redator", model=model)
            data = json.loads(raw)

            sections = {
                "quadro_clinico": data.get("quadro_clinico", ""),
                "falha_terapeutica": data.get("falha_terapeutica", ""),
                "justificativa_tecnica": data.get("justificativa_tecnica", ""),
                "evidencia_cientifica": data.get("evidencia_cientifica", ""),
                "risco_nao_realizacao": data.get("risco_nao_realizacao", ""),
                "conclusao": data.get("conclusao", ""),
            }
            # Compat: se o modelo antigo devolver justificativa_completa única, use-a.
            body = _assemble_body(sections) or data.get("justificativa_completa", "")
            return DraftReport(
                justificativa_completa=body,
                diagnostico_resumo=data.get("diagnostico_resumo", ""),
                quadro_clinico=data.get("quadro_clinico", ""),
                falha_terapeutica=data.get("falha_terapeutica", ""),
                justificativa_tecnica=data.get("justificativa_tecnica", ""),
                evidencia_cientifica=data.get("evidencia_cientifica", ""),
                risco_nao_realizacao=data.get("risco_nao_realizacao", ""),
                conclusao=data.get("conclusao", ""),
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
