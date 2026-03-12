"""
Testes para o modo Fora do Rol e Dossiê de Exceção.
Determinísticos e offline.
"""
import pytest

from app.services.compliance_layer import (
    ComplianceContext,
    build_writer_dut_prompt,
    _build_stf_checklist,
)
from app.services.tuss_validator import AnvisaStatusResult
from app.services.approval_score import compute_approval_score, PROHIBITED_TERMS
from app.services.dut_engine import DutEvaluation


class TestForaDoRolMode:
    def test_writer_prompt_includes_5_criteria(self):
        ctx = ComplianceContext(mode="fora_do_rol")
        prompt = build_writer_dut_prompt(ctx)
        assert "1." in prompt
        assert "2." in prompt
        assert "3." in prompt
        assert "4." in prompt
        assert "5." in prompt

    def test_writer_prompt_not_legal_opinion(self):
        ctx = ComplianceContext(mode="fora_do_rol")
        prompt = build_writer_dut_prompt(ctx)
        assert "NÃO parecer jurídico" in prompt

    def test_writer_prompt_mentions_alternatives(self):
        ctx = ComplianceContext(mode="fora_do_rol")
        prompt = build_writer_dut_prompt(ctx)
        assert "alternativa" in prompt.lower()


class TestDossieDeExcecao:
    def test_stf_checklist_complete_scenario(self):
        """Cenário: médico com CRM, declaração ANS, sem alternativa, evidência alta, Anvisa ativo."""
        result = _build_stf_checklist(
            medico_crm="54321-RJ",
            declaracao_ans=True,
            rol_alternatives=[],
            evidence_count=5,
            evidence_levels=["meta-analise", "rct"],
            anvisa_status=AnvisaStatusResult(registro="80117900999", status="ativo"),
        )
        assert result["all_met"] is True
        checklist = result["checklist"]
        for key, item in checklist.items():
            assert item["atendido"] is True, f"{key} not met"

    def test_stf_partial_scenario(self):
        """Cenário: sem CRM, sem declaração ANS."""
        result = _build_stf_checklist(
            evidence_count=2,
            evidence_levels=["coorte"],
        )
        assert result["all_met"] is False
        assert result["checklist"]["1_prescricao_medica"]["atendido"] is False
        assert result["checklist"]["2_sem_negativa_ans"]["atendido"] is False

    def test_alternatives_listed(self):
        class FakeProc:
            codigo_procedimento = "30001010"
            nome = "Procedimento alternativo X"

        result = _build_stf_checklist(
            rol_alternatives=[FakeProc()],
        )
        assert len(result["alternativas"]) == 1
        assert result["alternativas"][0]["codigo"] == "30001010"


class TestForaDoRolScore:
    def test_fora_do_rol_high_score_possible(self):
        """Mesmo fora do Rol, se tudo está completo, score pode ser alto."""
        score = compute_approval_score(
            dut_evaluation=None,
            evidence_count=5,
            evidence_levels=["meta-analise"],
            has_justification=True,
            anvisa_status=AnvisaStatusResult(registro="123", status="ativo"),
        )
        assert score.score >= 50

    def test_fora_do_rol_anvisa_vencido_critical(self):
        score = compute_approval_score(
            anvisa_status=AnvisaStatusResult(registro="123", status="vencido", alerta="Vencido"),
        )
        assert score.score <= 30
        assert len(score.alertas) > 0


class TestOutputLanguage:
    """Todos os outputs devem evitar linguagem de garantia."""

    def test_writer_prompt_no_guarantees(self):
        ctx = ComplianceContext(mode="fora_do_rol")
        prompt = build_writer_dut_prompt(ctx)
        for term in PROHIBITED_TERMS:
            assert term.lower() not in prompt.lower(), f"Proibido: {term}"

    def test_score_output_no_guarantees(self):
        score = compute_approval_score(
            evidence_count=10,
            evidence_levels=["meta-analise"],
            has_justification=True,
        )
        all_text = " ".join(score.explicacao + score.alertas + score.gaps)
        for term in PROHIBITED_TERMS:
            assert term.lower() not in all_text.lower(), f"Proibido: {term}"
