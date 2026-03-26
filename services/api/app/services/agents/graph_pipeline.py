"""
LangGraph-based pipeline for MedReport.

Replaces the linear ReportPipeline with a stateful directed graph that supports:
  - Conditional edges (DUT fail → fora do rol path)
  - Hallucination detection → loop back to writer (max 2 retries)
  - Human-in-the-loop (pause at questions node)
  - Automatic retry on transient failures

Graph:
  START → research → [questions?] → write → audit → validate → [contamination?] → END
                                      ↑                              │
                                      └──── hallucination_retry ─────┘
"""
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Annotated, TypedDict, Any

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)


# ── State ─────────────────────────────────────────────────────────────────

class PipelineState(TypedDict, total=False):
    """Shared state flowing through the graph."""
    # Input
    product: Any
    template: Any
    cid: str
    diagnostico: str
    medico_inputs: dict
    user_id: str

    # Research output
    clinical_evidences: list
    pubmed_evidences: list
    research_result: Any
    pending_questions: list
    tuss_selection: Any
    compliance_context: Any

    # Write output
    draft: Any
    consistency_score: float

    # Audit output
    audit_result: Any

    # Validation output
    validation: Any
    contamination: Any

    # Control flow
    step: str
    retry_count: int
    error: str
    final_result: dict


# ── Node functions ────────────────────────────────────────────────────────

async def research_node(state: PipelineState) -> PipelineState:
    """Execute Researcher agent (Agent A)."""
    from .researcher import research, _fetch_clinical_evidences, _fetch_pubmed_evidences

    product = state["product"]
    cid = state["cid"]
    diagnostico = state["diagnostico"]

    clinical_evidences = await _fetch_clinical_evidences(None, cid, product.id)
    pubmed_evidences = await _fetch_pubmed_evidences(None, cid, product.nome, diagnostico)

    research_result = await research(
        product, diagnostico, cid, state.get("template"), db=None,
    )

    questions = []
    if research_result.lacunas:
        questions = [
            {"secao": q.secao, "pergunta": q.pergunta, "opcoes": q.opcoes}
            for q in research_result.lacunas
        ]

    return {
        **state,
        "clinical_evidences": clinical_evidences,
        "pubmed_evidences": pubmed_evidences,
        "research_result": research_result,
        "pending_questions": questions,
        "step": "questions" if questions else "writing",
    }


async def write_node(state: PipelineState) -> PipelineState:
    """Execute Writer agent (Agent B)."""
    from .writer import write_justification

    draft = await write_justification(
        research=state["research_result"],
        product=state["product"],
        template=state.get("template"),
        medico_inputs=state["medico_inputs"],
        clinical_evidences=state.get("clinical_evidences", []),
        pubmed_evidences=state.get("pubmed_evidences", []),
    )

    return {
        **state,
        "draft": draft,
        "step": "auditing",
    }


async def audit_node(state: PipelineState) -> PipelineState:
    """Execute Auditor agent (Agent C)."""
    from .auditor import audit

    audit_result = await audit(
        state["draft"],
        state["product"],
        clinical_evidences=state.get("clinical_evidences", []),
        pubmed_evidences=state.get("pubmed_evidences", []),
    )

    return {
        **state,
        "audit_result": audit_result,
        "step": "validating",
    }


async def validate_node(state: PipelineState) -> PipelineState:
    """Execute hard-coded Validator (Layer 4) + contamination check."""
    from .validator import validate_technical_data

    validation = validate_technical_data(
        state["audit_result"].texto_corrigido,
        state["product"],
        medico_inputs=state["medico_inputs"],
    )

    # Contamination detection
    contamination = None
    try:
        from app.services.contamination_detector import check_contamination
        contamination = check_contamination(
            state["audit_result"].texto_corrigido,
            state["product"],
        )
    except Exception:
        pass

    return {
        **state,
        "validation": validation,
        "contamination": contamination,
        "step": "done",
        "retry_count": state.get("retry_count", 0),
    }


# ── Conditional edges ─────────────────────────────────────────────────────

def should_ask_questions(state: PipelineState) -> str:
    """After research: if there are questions, pause for human input."""
    if state.get("pending_questions"):
        return "wait_for_answers"
    return "write"


def should_retry_or_finish(state: PipelineState) -> str:
    """
    After validation: check for hallucinations.
    If found and retry_count < 2, loop back to writer.
    Otherwise, proceed to end.
    """
    validation = state.get("validation")
    contamination = state.get("contamination")
    retry_count = state.get("retry_count", 0)

    has_hallucination = False
    if validation and validation.has_blocking_issues:
        has_hallucination = True
    if contamination and hasattr(contamination, "has_blocking") and contamination.has_blocking:
        has_hallucination = True

    if has_hallucination and retry_count < 2:
        logger.warning(
            "Hallucination detected (retry %d/2), looping back to writer",
            retry_count + 1,
        )
        return "retry_write"

    return "finish"


async def increment_retry(state: PipelineState) -> PipelineState:
    """Increment retry counter before looping back to writer."""
    return {
        **state,
        "retry_count": state.get("retry_count", 0) + 1,
        "step": "writing",
    }


async def finish_node(state: PipelineState) -> PipelineState:
    """Assemble final result."""
    audit_result = state["audit_result"]
    validation = state["validation"]
    draft = state["draft"]

    final_approved = audit_result.aprovado and validation.aprovado
    if state.get("contamination") and hasattr(state["contamination"], "has_blocking"):
        if state["contamination"].has_blocking:
            final_approved = False

    result = {
        "step": "done",
        "justificativa": audit_result.texto_corrigido,
        "aprovado": final_approved,
        "checklist": audit_result.checklist,
        "audit_log": [
            {"tipo": a.tipo, "campo": a.campo, "original": a.original,
             "corrigido": a.corrigido, "motivo": a.motivo}
            for a in audit_result.audit_log
        ],
        "referencias": audit_result.referencias_validadas,
        "diagnostico_resumo": draft.diagnostico_resumo,
        "falha_terapeutica": draft.falha_terapeutica,
        "risco_nao_realizacao": draft.risco_nao_realizacao,
        "base_legal": draft.base_legal,
        "retry_count": state.get("retry_count", 0),
        "consistency_score": state.get("consistency_score", 0),
    }

    return {**state, "final_result": result, "step": "done"}


# ── Build Graph ───────────────────────────────────────────────────────────

def build_report_graph() -> StateGraph:
    """
    Build the LangGraph state machine for report generation.

    Usage:
        graph = build_report_graph()
        app = graph.compile()
        result = await app.ainvoke(initial_state)
    """
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("research", research_node)
    graph.add_node("write", write_node)
    graph.add_node("audit", audit_node)
    graph.add_node("validate", validate_node)
    graph.add_node("increment_retry", increment_retry)
    graph.add_node("finish", finish_node)

    # Add edges
    graph.set_entry_point("research")

    graph.add_conditional_edges(
        "research",
        should_ask_questions,
        {
            "wait_for_answers": END,  # Pause here — resume with answers
            "write": "write",
        },
    )

    graph.add_edge("write", "audit")
    graph.add_edge("audit", "validate")

    graph.add_conditional_edges(
        "validate",
        should_retry_or_finish,
        {
            "retry_write": "increment_retry",
            "finish": "finish",
        },
    )

    graph.add_edge("increment_retry", "write")
    graph.add_edge("finish", END)

    return graph


# ── Convenience function ──────────────────────────────────────────────────

_compiled_graph = None


async def run_graph_pipeline(
    product,
    template,
    cid: str,
    diagnostico: str,
    medico_inputs: dict,
    user_id: str = "",
) -> dict:
    """
    Run the full LangGraph pipeline.

    Returns the same result dict format as the legacy ReportPipeline.
    Falls back to legacy pipeline if LangGraph fails.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_report_graph().compile()

    initial_state: PipelineState = {
        "product": product,
        "template": template,
        "cid": cid,
        "diagnostico": diagnostico,
        "medico_inputs": medico_inputs,
        "user_id": user_id,
        "step": "init",
        "retry_count": 0,
    }

    try:
        final_state = await _compiled_graph.ainvoke(initial_state)

        if final_state.get("pending_questions"):
            return {
                "step": "questions",
                "questions": final_state["pending_questions"],
                "sugestao_tuss": getattr(final_state.get("research_result"), "sugestao_tuss", ""),
                "especialidade": getattr(final_state.get("research_result"), "especialidade_detectada", ""),
            }

        return final_state.get("final_result", {"error": "Pipeline did not produce result"})

    except Exception as e:
        logger.exception("LangGraph pipeline failed, falling back to legacy: %s", e)
        return {"error": f"LangGraph failed: {e}"}
