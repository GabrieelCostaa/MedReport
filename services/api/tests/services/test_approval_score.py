"""
Testes unitários para ApprovalScore.
Determinísticos e offline.
Testa pesos, monotonicidade, alertas críticos e ausência de linguagem de garantia.
"""
import pytest

from app.services.dut_engine import DutEvaluation, CriterionResult
from app.services.tuss_validator import TussValidation, AnvisaStatusResult
from app.services.approval_score import compute_approval_score, PROHIBITED_TERMS, ApprovalScore


def _make_evaluation(met=3, unmet=0, unknown=0, subjective=0, exclusion=False):
    """Helper para criar DutEvaluation com quantidades específicas."""
    e = DutEvaluation()
    for i in range(met):
        e.criteria_met.append(CriterionResult(id=f"M{i}", tipo="deterministico", resultado="met"))
    for i in range(unmet):
        e.criteria_unmet.append(CriterionResult(id=f"U{i}", tipo="deterministico", resultado="unmet"))
    for i in range(unknown):
        e.criteria_unknown.append(CriterionResult(id=f"K{i}", tipo="deterministico", resultado="unknown"))
    for i in range(subjective):
        e.criteria_subjective.append(CriterionResult(id=f"S{i}", tipo="subjetivo", resultado="unknown"))
    if exclusion:
        e.exclusion_triggered = CriterionResult(id="EX1", tipo="exclusao", resultado="unmet", mensagem="Uso estético")
    return e


class TestScoreNiveis:
    def test_alto(self):
        ev = _make_evaluation(met=5)
        score = compute_approval_score(
            dut_evaluation=ev,
            tuss_validation=TussValidation(codigo="123", valido=True),
            evidence_count=3,
            evidence_levels=["meta-analise"],
            has_justification=True,
        )
        assert score.nivel == "alto"
        assert score.score >= 80

    def test_medio(self):
        from app.services.tuss_validator import TissValidation
        ev = _make_evaluation(met=3, unknown=2)
        score = compute_approval_score(
            dut_evaluation=ev,
            tuss_validation=TussValidation(codigo="123", valido=True),
            tiss_validation=TissValidation(tipo_guia="SP/SADT", campo="Mat/Med", codigo="123", permitido=True),
            evidence_count=1,
            has_justification=True,
        )
        assert score.nivel in ("medio", "alto")

    def test_critico_exclusion(self):
        ev = _make_evaluation(met=3, exclusion=True)
        score = compute_approval_score(dut_evaluation=ev)
        assert score.score < 60
        assert len(score.alertas) > 0

    def test_critico_no_data(self):
        score = compute_approval_score()
        assert score.nivel in ("baixo", "critico", "medio")


class TestScoreComponentes:
    def test_all_components_present(self):
        score = compute_approval_score(
            dut_evaluation=_make_evaluation(met=5),
            tuss_validation=TussValidation(codigo="123", valido=True),
            evidence_count=2,
            has_justification=True,
        )
        assert "aderencia_dut" in score.componentes
        assert "completude_tiss_tuss" in score.componentes
        assert "qualidade_justificativa" in score.componentes
        assert "robustez_evidencia" in score.componentes

    def test_dut_component_max_40(self):
        ev = _make_evaluation(met=10)
        score = compute_approval_score(dut_evaluation=ev)
        assert score.componentes["aderencia_dut"] <= 40

    def test_evidence_component_max_10(self):
        score = compute_approval_score(evidence_count=100, evidence_levels=["meta-analise"])
        assert score.componentes["robustez_evidencia"] <= 10

    def test_score_never_exceeds_100(self):
        score = compute_approval_score(
            dut_evaluation=_make_evaluation(met=10),
            tuss_validation=TussValidation(codigo="123", valido=True),
            evidence_count=10,
            evidence_levels=["meta-analise"],
            has_justification=True,
        )
        assert score.score <= 100


class TestAnvisaImpact:
    def test_vencido_caps_score(self):
        ev = _make_evaluation(met=5)
        score = compute_approval_score(
            dut_evaluation=ev,
            tuss_validation=TussValidation(codigo="123", valido=True),
            anvisa_status=AnvisaStatusResult(registro="123", status="vencido", alerta="Vencido"),
            evidence_count=3,
            evidence_levels=["meta-analise"],
            has_justification=True,
        )
        assert score.score <= 30
        assert any("vencido" in a.lower() for a in score.alertas)

    def test_ativo_no_penalty(self):
        ev = _make_evaluation(met=5)
        score_ativo = compute_approval_score(
            dut_evaluation=ev,
            anvisa_status=AnvisaStatusResult(registro="123", status="ativo"),
        )
        score_sem = compute_approval_score(dut_evaluation=ev)
        assert score_ativo.score >= score_sem.score - 5


class TestMonotonicidade:
    """Mais dados completos -> score não cai."""

    def test_more_met_same_or_higher(self):
        score_low = compute_approval_score(dut_evaluation=_make_evaluation(met=1, unmet=2))
        score_high = compute_approval_score(dut_evaluation=_make_evaluation(met=3))
        assert score_high.score >= score_low.score

    def test_adding_evidence_helps(self):
        base = compute_approval_score(evidence_count=0)
        with_ev = compute_approval_score(evidence_count=3, evidence_levels=["meta-analise"])
        assert with_ev.score >= base.score

    def test_adding_justification_helps(self):
        base = compute_approval_score(has_justification=False)
        with_just = compute_approval_score(has_justification=True)
        assert with_just.score >= base.score


class TestLinguagemGarantia:
    """Nenhum output pode conter linguagem de garantia."""

    def test_no_prohibited_terms_in_explanation(self):
        score = compute_approval_score(
            dut_evaluation=_make_evaluation(met=5),
            tuss_validation=TussValidation(codigo="123", valido=True),
            evidence_count=5,
            evidence_levels=["meta-analise"],
            has_justification=True,
        )
        all_text = " ".join(score.explicacao + score.alertas + score.gaps)
        for term in PROHIBITED_TERMS:
            assert term.lower() not in all_text.lower(), f"Termo proibido encontrado: {term}"


class TestGaps:
    def test_unmet_generates_gap(self):
        ev = _make_evaluation(met=2, unmet=1)
        score = compute_approval_score(dut_evaluation=ev)
        assert len(score.gaps) > 0

    def test_no_evidence_generates_gap(self):
        score = compute_approval_score(evidence_count=0)
        assert any("evidência" in g.lower() for g in score.gaps)

    def test_no_justification_generates_gap(self):
        score = compute_approval_score(has_justification=False)
        assert any("justificativa" in g.lower() for g in score.gaps)
