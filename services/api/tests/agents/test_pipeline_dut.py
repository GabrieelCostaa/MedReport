"""
Testes unitários para compliance_layer e integração DUT-aware.
Determinísticos e offline.
"""
import pytest

from app.services.dut_engine import evaluate_dsl, build_evaluation, DutEvaluation, CriterionResult
from app.services.compliance_layer import (
    build_writer_dut_prompt,
    build_auditor_compliance_instructions,
    ComplianceContext,
    StfChecklist,
    _build_stf_checklist,
)
from app.services.tuss_validator import AnvisaStatusResult


VISCOSUP_DSL = {
    "criterios": [
        {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": 18, "descricao": "Idade >= 18"},
        {"id": "B", "tipo": "deterministico", "campo_paciente": "grau_kellgren_lawrence", "operador": "in", "valor": [2, 3], "descricao": "KL 2-3"},
    ],
    "exclusoes": [],
    "logica": "A AND B",
}


class TestComplianceContext:
    def test_default_mode(self):
        ctx = ComplianceContext()
        assert ctx.mode == "cobertura_direta"

    def test_fora_do_rol_mode(self):
        ctx = ComplianceContext(mode="fora_do_rol")
        assert ctx.mode == "fora_do_rol"


class TestWriterDutPrompt:
    def test_cobertura_direta_empty(self):
        ctx = ComplianceContext(mode="cobertura_direta")
        prompt = build_writer_dut_prompt(ctx)
        assert prompt == ""

    def test_rol_dut_includes_instructions(self):
        class FakeDut:
            numero_dut = "10"
            criterios_texto = "Texto da DUT 10..."
        
        results = evaluate_dsl(VISCOSUP_DSL, {"idade": 55, "grau_kellgren_lawrence": 3})
        evaluation = build_evaluation(results)
        
        ctx = ComplianceContext(
            mode="rol_dut",
            dut_rule=FakeDut(),
            dut_evaluation=evaluation,
            dut_criteria_text="Texto da DUT 10...",
        )
        prompt = build_writer_dut_prompt(ctx)
        assert "DUT 10" in prompt
        assert "COMPLIANCE" in prompt

    def test_fora_do_rol_includes_legal_basis(self):
        ctx = ComplianceContext(mode="fora_do_rol")
        prompt = build_writer_dut_prompt(ctx)
        assert "Lei 14.454/2022" in prompt
        assert "STF" in prompt
        assert "ADI 7.265" in prompt

    def test_fora_do_rol_mentions_alternatives(self):
        ctx = ComplianceContext(mode="fora_do_rol")
        prompt = build_writer_dut_prompt(ctx)
        assert "alternativa" in prompt.lower()


class TestAuditorInstructions:
    def test_empty_when_no_dut(self):
        ctx = ComplianceContext(mode="cobertura_direta")
        instructions = build_auditor_compliance_instructions(ctx)
        assert instructions == ""

    def test_includes_met_criteria(self):
        results = evaluate_dsl(VISCOSUP_DSL, {"idade": 55, "grau_kellgren_lawrence": 3})
        evaluation = build_evaluation(results)
        ctx = ComplianceContext(mode="rol_dut", dut_evaluation=evaluation)
        instructions = build_auditor_compliance_instructions(ctx)
        assert "[OK]" in instructions

    def test_includes_unmet_criteria(self):
        results = evaluate_dsl(VISCOSUP_DSL, {"idade": 15, "grau_kellgren_lawrence": 3})
        evaluation = build_evaluation(results)
        ctx = ComplianceContext(mode="rol_dut", dut_evaluation=evaluation)
        instructions = build_auditor_compliance_instructions(ctx)
        assert "[FALTA]" in instructions

    def test_anvisa_alert(self):
        ctx = ComplianceContext(
            mode="rol_dut",
            anvisa_status=AnvisaStatusResult(
                registro="123", status="vencido", alerta="Registro vencido"
            ),
        )
        instructions = build_auditor_compliance_instructions(ctx)
        assert "ANVISA" in instructions


class TestStfChecklist:
    def test_all_met(self):
        checklist_data = _build_stf_checklist(
            medico_crm="12345-SP",
            declaracao_ans=True,
            rol_alternatives=[],
            evidence_count=5,
            evidence_levels=["meta-analise"],
            anvisa_status=AnvisaStatusResult(registro="123", status="ativo"),
        )
        assert checklist_data["all_met"] is True

    def test_missing_crm(self):
        checklist_data = _build_stf_checklist()
        checklist = checklist_data["checklist"]
        assert checklist["1_prescricao_medica"]["atendido"] is False

    def test_declaratorio_sem_negativa(self):
        checklist_data = _build_stf_checklist(declaracao_ans=False)
        checklist = checklist_data["checklist"]
        assert checklist["2_sem_negativa_ans"]["tipo"] == "declaratorio"
        assert checklist["2_sem_negativa_ans"]["atendido"] is False

    def test_anvisa_not_met(self):
        checklist_data = _build_stf_checklist(
            anvisa_status=AnvisaStatusResult(registro="123", status="vencido"),
        )
        checklist = checklist_data["checklist"]
        assert checklist["5_registro_anvisa"]["atendido"] is False

    def test_evidence_high_level(self):
        checklist_data = _build_stf_checklist(
            evidence_count=3,
            evidence_levels=["rct", "meta-analise"],
        )
        checklist = checklist_data["checklist"]
        assert checklist["4_evidencia_cientifica"]["atendido"] is True
        assert checklist["4_evidencia_cientifica"]["nivel"] == "alto"


class TestStfChecklistClass:
    def test_to_dict_has_all_keys(self):
        checklist = StfChecklist()
        d = checklist.to_dict()
        assert "1_prescricao_medica" in d
        assert "2_sem_negativa_ans" in d
        assert "3_sem_alternativa_rol" in d
        assert "4_evidencia_cientifica" in d
        assert "5_registro_anvisa" in d

    def test_not_all_met_by_default(self):
        checklist = StfChecklist()
        assert checklist.all_met is False
