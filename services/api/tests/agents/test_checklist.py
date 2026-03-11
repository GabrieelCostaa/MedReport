"""
Testes unitários para o Checklist de Saída.
Valida que os 6 itens obrigatórios são avaliados corretamente.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.services.agents.checklist import ReportChecklist, REQUIRED_SECTIONS
from tests.conftest import MockReport


class TestRequiredSections:
    def test_all_six_sections_defined(self):
        assert len(REQUIRED_SECTIONS) == 6
        expected = {
            "diagnostico",
            "justificativa_tecnica",
            "falha_terapeutica",
            "risco_nao_realizacao",
            "base_legal_ans",
            "referencia_bibliografica",
        }
        assert set(REQUIRED_SECTIONS.keys()) == expected


class TestChecklistEvaluate:
    def test_complete_report_all_ok(self, complete_report):
        checklist = ReportChecklist.evaluate(complete_report)
        for key, item in checklist.items():
            assert item["ok"] is True, f"Item '{key}' deveria ser True"
        assert len(checklist) == 6

    def test_incomplete_report_fails(self, incomplete_report):
        checklist = ReportChecklist.evaluate(incomplete_report)
        failed = [k for k, v in checklist.items() if not v["ok"]]
        assert len(failed) >= 3

    def test_missing_diagnosis_fails(self):
        report = MockReport(
            diagnosis="",
            justificativa_ia="Texto longo " * 20,
            falha_terapeutica="Fisioterapia falhou",
            risco_nao_realizacao="Progressão da doença",
            base_legal_ans="RN 395",
            referencias_bib=["Altman 2015"],
        )
        checklist = ReportChecklist.evaluate(report)
        assert checklist["diagnostico"]["ok"] is False

    def test_short_diagnosis_fails(self):
        report = MockReport(diagnosis="abc")
        checklist = ReportChecklist.evaluate(report)
        assert checklist["diagnostico"]["ok"] is False

    def test_short_justificativa_fails(self):
        report = MockReport(justificativa_ia="Muito curto")
        checklist = ReportChecklist.evaluate(report)
        assert checklist["justificativa_tecnica"]["ok"] is False

    def test_empty_falha_terapeutica_fails(self):
        report = MockReport(falha_terapeutica="")
        checklist = ReportChecklist.evaluate(report)
        assert checklist["falha_terapeutica"]["ok"] is False

    def test_empty_risco_fails(self):
        report = MockReport(risco_nao_realizacao="")
        checklist = ReportChecklist.evaluate(report)
        assert checklist["risco_nao_realizacao"]["ok"] is False

    def test_missing_base_legal_fails(self):
        report = MockReport(
            base_legal_ans="",
            justificativa_ia="Texto sem menção à ANS" * 10,
        )
        checklist = ReportChecklist.evaluate(report)
        assert checklist["base_legal_ans"]["ok"] is False

    def test_base_legal_in_text_passes(self):
        report = MockReport(
            base_legal_ans="",
            justificativa_ia="Conforme a RN 395 da ANS, o material é indicado. " * 5,
        )
        checklist = ReportChecklist.evaluate(report)
        assert checklist["base_legal_ans"]["ok"] is True

    def test_empty_references_fails(self):
        report = MockReport(referencias_bib=[])
        checklist = ReportChecklist.evaluate(report)
        assert checklist["referencia_bibliografica"]["ok"] is False

    def test_null_references_fails(self):
        report = MockReport(referencias_bib=None)
        checklist = ReportChecklist.evaluate(report)
        assert checklist["referencia_bibliografica"]["ok"] is False


class TestChecklistIsApproved:
    def test_complete_report_approved(self, complete_report):
        assert ReportChecklist.is_approved(complete_report) is True

    def test_incomplete_report_not_approved(self, incomplete_report):
        assert ReportChecklist.is_approved(incomplete_report) is False


class TestChecklistMissingItems:
    def test_complete_no_missing(self, complete_report):
        missing = ReportChecklist.missing_items(complete_report)
        assert len(missing) == 0

    def test_incomplete_lists_missing(self, incomplete_report):
        missing = ReportChecklist.missing_items(incomplete_report)
        assert len(missing) >= 3
        assert all(isinstance(m, str) for m in missing)

    def test_single_missing_item(self):
        report = MockReport(
            diagnosis="Gonartrose grau III CID M17.0",
            justificativa_ia="Texto completo " * 20 + "RN 395 da ANS",
            falha_terapeutica="Fisioterapia por 6 meses sem melhora",
            risco_nao_realizacao="",
            base_legal_ans="RN 395",
            referencias_bib=["Altman 2015"],
        )
        missing = ReportChecklist.missing_items(report)
        assert len(missing) == 1
        assert "Risco" in missing[0]
