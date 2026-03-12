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
    else:
        dut_score = 20.0
        explanations.append("DUT não avaliada — score parcial (20/40)")

    components["aderencia_dut"] = round(dut_score, 1)

    # 2. Completude TISS/TUSS (0-30)
    tiss_score = 0.0

    if tuss_validation:
        if tuss_validation.valido:
            tiss_score += 15.0
            explanations.append(f"Código TUSS {tuss_validation.codigo} válido (15/15)")
        else:
            alerts.append(f"Código TUSS inválido: {tuss_validation.mensagem}")
            gaps.append(f"Código TUSS {tuss_validation.codigo}: {tuss_validation.mensagem}")
    else:
        tiss_score += 7.5
        gaps.append("Código TUSS não validado contra base oficial")

    if tiss_validation and tiss_validation is not None:
        tiss_score += 7.5

    if tiss_validation:
        if isinstance(tiss_validation, TissValidation):
            pass
        else:
            tiss_score += 7.5

    if tiss_validation:
        tiss_score = min(tiss_score, 22.5)

    tiss_score += 7.5  # Base for having any structure

    tiss_score = min(30.0, tiss_score)
    components["completude_tiss_tuss"] = round(tiss_score, 1)

    if tiss_validation and hasattr(tiss_validation, 'permitido'):
        if not tiss_validation.permitido:
            tiss_score = 0
            alerts.append(f"GLOSA TISS: {tiss_validation.mensagem}")
            components["completude_tiss_tuss"] = 0

    # 3. Qualidade da justificativa (0-20)
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
