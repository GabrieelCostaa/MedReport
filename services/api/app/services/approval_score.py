"""
Score de Aprovação Explicável.

Componentes (explanable-by-design):
- Aderência DUT (0-40): % critérios atendidos + evidência anexada
- Completude estrutural TISS/TUSS (0-30): códigos corretos, campos preenchidos
- Qualidade da justificativa (0-20): template DUT-citado, coerência
- Robustez da evidência (0-10): nível da literatura

IMPORTANTE: Score sempre com explicação + gaps, NUNCA com promessa de aprovação.
Linguagem: "completude documental estimada", não "chance de aprovação".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.dut_engine import DutEvaluation
from app.services.tuss_validator import TussValidation, TissValidation, AnvisaStatusResult


@dataclass
class ApprovalScore:
    score: float  # 0-100
    nivel: str  # alto | medio | baixo | critico
    componentes: dict = field(default_factory=dict)
    explicacao: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)


PROHIBITED_TERMS = [
    "garantido", "garantia", "certeza", "aprovação garantida",
    "será aprovado", "com certeza", "100% de chance",
]


def compute_approval_score(
    dut_evaluation: DutEvaluation | None = None,
    tuss_validation: TussValidation | None = None,
    tiss_validation: TissValidation | None = None,
    anvisa_status: AnvisaStatusResult | None = None,
    evidence_count: int = 0,
    evidence_levels: list[str] | None = None,
    has_justification: bool = False,
    cid_procedure_consistent: bool = True,
    compliance_mode: str = "",
    stf_checklist: dict | None = None,
    operadora_glosa=None,  # OperadoraGlosaSummary — INFORMATIVO, não altera o score
    quality_scores: dict | None = None,  # {"faithfulness": .., "relevancy": .., "citation": ..}
) -> ApprovalScore:
    """Calcula score de completude documental estimada."""

    components = {}
    explanations = []
    alerts = []
    gaps = []

    # 1. Aderência DUT (0-40)
    dut_score = 0.0
    if dut_evaluation:
        total = dut_evaluation.total_criteria
        if total > 0:
            met_ratio = len(dut_evaluation.criteria_met) / total
            dut_score = met_ratio * 40.0

            if dut_evaluation.criteria_unmet:
                for c in dut_evaluation.criteria_unmet:
                    gaps.append(f"Critério DUT {c.id} não atendido: {c.mensagem}")

            if dut_evaluation.criteria_unknown:
                for c in dut_evaluation.criteria_unknown:
                    gaps.append(f"Dado faltante para DUT: {c.mensagem}")
                dut_score *= 0.8

            if dut_evaluation.documents_missing:
                penalty = min(len(dut_evaluation.documents_missing) * 5, 15)
                dut_score = max(0, dut_score - penalty)
                for d in dut_evaluation.documents_missing:
                    gaps.append(f"Documento exigido pela DUT não fornecido: {d}")

            if dut_evaluation.exclusion_triggered:
                dut_score = 0
                alerts.append(
                    f"EXCLUSÃO ATIVADA: {dut_evaluation.exclusion_triggered.mensagem}"
                )

            explanations.append(
                f"Aderência DUT: {len(dut_evaluation.criteria_met)}/{total} critérios atendidos "
                f"({dut_score:.0f}/40)"
            )
        else:
            dut_score = 40.0
            explanations.append("Procedimento sem DUT condicionante — cobertura direta (40/40)")
    elif compliance_mode == "cobertura_direta":
        # Procedimento no Rol sem DUT — cobertura obrigatória
        dut_score = 40.0
        explanations.append("Procedimento no Rol sem DUT condicionante — cobertura direta (40/40)")
    elif compliance_mode == "fora_do_rol" and stf_checklist:
        # Fora do Rol: usar checklist STF (5 critérios cumulativos) como proxy
        checklist_items = stf_checklist.get("checklist", {})
        met = sum(1 for v in checklist_items.values() if isinstance(v, dict) and v.get("atendido"))
        total_stf = max(len(checklist_items), 1)
        dut_score = (met / total_stf) * 40.0
        explanations.append(
            f"Fora do Rol — checklist STF: {met}/{total_stf} critérios atendidos ({dut_score:.0f}/40)"
        )
        if met < total_stf:
            for key, val in checklist_items.items():
                if isinstance(val, dict) and not val.get("atendido"):
                    gaps.append(f"Critério STF não atendido: {key}")
    else:
        dut_score = 20.0
        explanations.append("DUT não avaliada — score parcial (20/40)")

    components["aderencia_dut"] = round(dut_score, 1)

    # 2. Completude TISS/TUSS (0-30)
    # TUSS code validation (0-15)
    tuss_component = 0.0
    if tuss_validation:
        if tuss_validation.valido:
            tuss_component = 15.0
            explanations.append(f"Código TUSS {tuss_validation.codigo} válido (15/15)")
        else:
            alerts.append(f"Código TUSS inválido: {tuss_validation.mensagem}")
            gaps.append(f"Código TUSS {tuss_validation.codigo}: {tuss_validation.mensagem}")
    else:
        gaps.append("Código TUSS não validado contra base oficial")

    # TISS field validation (0-15)
    tiss_component = 0.0
    if tiss_validation:
        if tiss_validation.permitido:
            tiss_component = 15.0
            explanations.append(f"Campo TISS validado: {tiss_validation.campo} ({tiss_validation.tipo_guia})")
        else:
            alerts.append(f"GLOSA TISS: {tiss_validation.mensagem}")
            gaps.append(f"Código TUSS no campo TISS incorreto: {tiss_validation.mensagem}")
    else:
        gaps.append("Validação TISS não realizada (tabela tiss_rules vazia ou não consultada)")

    tiss_score = min(30.0, tuss_component + tiss_component)
    components["completude_tiss_tuss"] = round(tiss_score, 1)

    # 3. Qualidade da justificativa (0-20)
    # Com métricas medidas (fidelidade/relevância/citação, cada uma em [0,1]),
    # os 20 pts refletem a qualidade REAL do texto. Sem elas, fallback ao
    # booleano legado ("texto existe" + CID consistente).
    quality_vals = [
        v for v in (quality_scores or {}).values()
        if isinstance(v, (int, float)) and 0.0 <= v <= 1.0
    ]
    if quality_vals:
        just_score = 20.0 * (sum(quality_vals) / len(quality_vals))
        if not has_justification:
            just_score = 0.0
            gaps.append("Justificativa não gerada")
        if not cid_procedure_consistent:
            just_score = min(just_score, 10.0)
            gaps.append("Inconsistência entre CID e procedimento solicitado")
            alerts.append("CID pode não ser compatível com o procedimento")
        f = (quality_scores or {}).get("faithfulness")
        if isinstance(f, (int, float)) and f < 0.7:
            alerts.append(
                f"Fidelidade à evidência abaixo do esperado ({f:.0%}) — revise afirmações sinalizadas"
            )
    else:
        just_score = 0.0
        if has_justification:
            just_score += 10.0
        else:
            gaps.append("Justificativa não gerada")

        if cid_procedure_consistent:
            just_score += 10.0
        else:
            gaps.append("Inconsistência entre CID e procedimento solicitado")
            alerts.append("CID pode não ser compatível com o procedimento")

    components["qualidade_justificativa"] = round(just_score, 1)

    # 4. Robustez da evidência (0-10)
    ev_score = 0.0
    levels = evidence_levels or []
    level_weights = {
        "meta-analise": 10, "meta_analise": 10, "revisao-sistematica": 9,
        "rct": 8, "ecr": 8, "ensaio_clinico": 8,
        "coorte": 6, "caso-controle": 5,
        "serie_casos": 3, "relato_caso": 2, "opiniao_especialista": 1,
    }
    if levels:
        max_level = max(level_weights.get(l.lower().replace(" ", "_"), 2) for l in levels)
        ev_score = min(10.0, max_level)
    elif evidence_count > 0:
        ev_score = min(7.0, evidence_count * 2.0)
    else:
        gaps.append("Nenhuma evidência científica anexada")

    components["robustez_evidencia"] = round(ev_score, 1)

    # Anvisa check (modifica alerts, pode zerar score)
    if anvisa_status:
        if anvisa_status.status in ("vencido", "suspenso", "cancelado"):
            alerts.append(
                f"CRÍTICO: Registro Anvisa {anvisa_status.registro} está {anvisa_status.status}. "
                f"Critério 5 do STF (ADI 7.265) não atendido."
            )
            components["anvisa_status"] = anvisa_status.status
        elif anvisa_status.status == "desconhecido":
            gaps.append("Status Anvisa não verificado")
            components["anvisa_status"] = "desconhecido"
        else:
            components["anvisa_status"] = "ativo"

    # Risco da operadora (Painel de Glosas ANS) — informativo: entra em alertas e
    # componentes surfaced, mas NUNCA no somatório do score (o comportamento da
    # operadora não é mérito do laudo do médico).
    if operadora_glosa is not None:
        pc = (getattr(operadora_glosa, "medias_recentes", None) or {}).get("pc_glosa_inicial")
        if pc is not None:
            hist = " (dados históricos)" if getattr(operadora_glosa, "is_stale", False) else ""
            alerts.append(
                f"Convênio {operadora_glosa.razao_social} (ANS {operadora_glosa.registro_ans}): "
                f"glosa inicial média de {pc:.1f}% nos últimos {operadora_glosa.n_semestres} "
                f"semestres do Painel de Glosas ANS{hist} — informativo, não altera o score."
            )
        components["operadora_glosa"] = {
            "registro_ans": getattr(operadora_glosa, "registro_ans", ""),
            "medias_recentes": getattr(operadora_glosa, "medias_recentes", {}),
            "periodo": getattr(operadora_glosa, "period_range", ""),
        }
        if getattr(operadora_glosa, "ambiguous", False):
            gaps.append(
                "Nome do convênio ambíguo — confirme a operadora "
                "(múltiplas correspondências no Painel de Glosas ANS)."
            )

    total = sum([
        components["aderencia_dut"],
        components["completude_tiss_tuss"],
        components["qualidade_justificativa"],
        components["robustez_evidencia"],
    ])

    if anvisa_status and anvisa_status.status in ("vencido", "suspenso", "cancelado"):
        total = min(total, 30.0)

    total = round(min(100.0, max(0.0, total)), 1)

    if total >= 80:
        nivel = "alto"
    elif total >= 60:
        nivel = "medio"
    elif total >= 40:
        nivel = "baixo"
    else:
        nivel = "critico"

    return ApprovalScore(
        score=total,
        nivel=nivel,
        componentes=components,
        explicacao=explanations,
        alertas=alerts,
        gaps=gaps,
    )
