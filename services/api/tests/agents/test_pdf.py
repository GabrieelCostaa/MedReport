"""
Testes unitários para geração de PDF.
Valida que o arquivo gerado contém os campos obrigatórios.
"""
import pytest
import sys
import os
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from datetime import datetime


class MockReportForPdf:
    """Report mock com todos os atributos que o gerador de PDF espera."""
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", uuid.uuid4())
        self.cid = kwargs.get("cid", "M17.0")
        self.diagnosis = kwargs.get("diagnosis", "Gonartrose bilateral")
        self.surgery_description = kwargs.get("surgery_description", "Viscossuplementação")
        self.materials = kwargs.get("materials", "Kit EC2 - Linha Opus")
        self.health_plan = kwargs.get("health_plan", "Unimed")
        self.tuss_codes = kwargs.get("tuss_codes", [{"code": "20104120", "term": "Viscossuplementação"}])
        self.justificativa_ia = kwargs.get("justificativa_ia", "")
        self.created_at = kwargs.get("created_at", datetime.utcnow())
        self.paciente_nome = kwargs.get("paciente_nome", "Ana Costa")
        self.especialidade = kwargs.get("especialidade", "Ortopedia")
        self.falha_terapeutica = kwargs.get("falha_terapeutica", "")
        self.risco_nao_realizacao = kwargs.get("risco_nao_realizacao", "")
        self.base_legal_ans = kwargs.get("base_legal_ans", "")
        self.referencias_bib = kwargs.get("referencias_bib", [])
        self.signed_at = None


class TestBuildGuiaXml:
    def test_xml_contains_cid(self):
        from app.services.tiss import build_guia_solicitacao_xml
        report = MockReportForPdf(cid="M17.0")
        xml = build_guia_solicitacao_xml(report)
        assert "M17.0" in xml
        assert "<?xml" in xml

    def test_xml_contains_diagnosis(self):
        from app.services.tiss import build_guia_solicitacao_xml
        report = MockReportForPdf(diagnosis="Gonartrose bilateral")
        xml = build_guia_solicitacao_xml(report)
        assert "Gonartrose bilateral" in xml

    def test_xml_contains_justificativa(self):
        from app.services.tiss import build_guia_solicitacao_xml
        report = MockReportForPdf(
            justificativa_ia="Justificativa técnica completa do procedimento"
        )
        xml = build_guia_solicitacao_xml(report)
        assert "justificativaTecnica" in xml


class TestBuildReportHtml:
    def test_html_contains_patient(self):
        from app.services.tiss import _build_report_html
        report = MockReportForPdf(paciente_nome="João Silva")
        html = _build_report_html(report)
        assert "João Silva" in html

    def test_html_contains_cid(self):
        from app.services.tiss import _build_report_html
        report = MockReportForPdf(cid="M17.0")
        html = _build_report_html(report)
        assert "M17.0" in html

    def test_html_contains_justificativa(self):
        from app.services.tiss import _build_report_html
        report = MockReportForPdf(
            justificativa_ia="A viscossuplementação com ácido hialurônico é indicada."
        )
        html = _build_report_html(report)
        assert "viscossuplementação" in html

    def test_html_contains_base_legal(self):
        from app.services.tiss import _build_report_html
        report = MockReportForPdf(base_legal_ans="RN 395 da ANS")
        html = _build_report_html(report)
        assert "RN 395" in html
        assert "Fundamentação Legal" in html

    def test_html_contains_references(self):
        from app.services.tiss import _build_report_html
        report = MockReportForPdf(
            referencias_bib=["Altman RD, 2015", "Bellamy N, 2006"]
        )
        html = _build_report_html(report)
        assert "Altman RD" in html
        assert "Referências Bibliográficas" in html

    def test_html_has_required_structure(self):
        from app.services.tiss import _build_report_html
        report = MockReportForPdf(
            paciente_nome="Maria S.",
            cid="K66.0",
            especialidade="Cirurgia Geral",
            justificativa_ia="Texto da justificativa técnica completa.",
            base_legal_ans="RN 395",
            referencias_bib=["Diamond 1996"],
        )
        html = _build_report_html(report)
        assert "RELATÓRIO MÉDICO" in html
        assert "Justificativa Técnica" in html
        assert "Médico Responsável" in html
        assert "CRM" in html

    def test_html_with_empty_fields(self):
        """Teste que o HTML é gerado mesmo com campos vazios (fallback)."""
        from app.services.tiss import _build_report_html
        report = MockReportForPdf(
            paciente_nome="",
            cid="",
            diagnosis="",
            justificativa_ia="",
        )
        html = _build_report_html(report)
        assert "<!DOCTYPE html>" in html
        assert "RELATÓRIO MÉDICO" in html


class TestPdfGeneration:
    def test_pdf_generates_bytes(self):
        """Testa que o PDF é gerado como bytes (não vazio)."""
        from app.services.tiss import build_guia_pdf
        report = MockReportForPdf(
            paciente_nome="Ana Costa",
            cid="M17.0",
            diagnosis="Gonartrose",
            justificativa_ia="Justificativa técnica completa " * 10,
        )
        pdf_bytes = build_guia_pdf(report)
        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 100
        assert pdf_bytes[:4] == b"%PDF" or pdf_bytes[:5] == b"%PDF-"
