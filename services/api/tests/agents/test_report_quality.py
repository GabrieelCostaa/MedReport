"""
Cobre as melhorias de qualidade do laudo:
- montagem do corpo a partir das seções (writer._assemble_body)
- split do corpo em seções para o PDF (pdf_generator._split_into_sections)
- strippers do Auditor viram flag-and-rewrite (não apagam a frase clínica)
- geração de PDF com as seções e campos anti-glosa
"""
import os

os.environ.setdefault("SECRET_KEY", "chave-de-teste-para-pytest-nao-usar-em-producao-64chars!!")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_local.db")

from app.services.agents.writer import _assemble_body, _SECTION_TITLES
from app.services.pdf_generator import _split_into_sections, generate_pdf_bytes
from app.services.agents.auditor import _strip_fabricated_costs, _strip_legal_from_body


SECTIONS = {
    "quadro_clinico": "Paciente com gonartrose grau III (CID M17.1).",
    "falha_terapeutica": "AINEs e fisioterapia por 14 semanas, sem melhora.",
    "justificativa_tecnica": "Hialuronato de alto peso molecular promove viscoindução.",
    "evidencia_cientifica": "Meta-análise favorável (Altman et al., 2015).",
    "risco_nao_realizacao": "Progressão para grau IV e artroplastia.",
    "conclusao": "Solicita-se a liberação do material.",
}


class TestSectionRoundTrip:
    def test_assemble_body_has_all_titles(self):
        body = _assemble_body(SECTIONS)
        for _key, titulo in _SECTION_TITLES:
            assert titulo in body

    def test_split_recovers_six_sections(self):
        body = _assemble_body(SECTIONS)
        secs = _split_into_sections(body)
        assert len(secs) == 6
        # cada seção deve ter pelo menos 1 parágrafo com conteúdo
        assert all(s["paragrafos"] for s in secs)

    def test_split_falls_back_to_single_section(self):
        """Sem títulos reconhecidos, cai para 'Justificativa Técnica' única."""
        secs = _split_into_sections("Texto corrido sem títulos de seção nenhum.")
        assert len(secs) == 1
        assert secs[0]["titulo"] == "Justificativa Técnica"


class TestAuditorStrippersFlagNotDelete:
    def test_bare_money_removed_but_sentence_kept(self):
        text = "O material custa R$ 5.000 e reduz o tempo cirúrgico de forma relevante."
        out, entries = _strip_fabricated_costs(text, evidences=[])
        # a frase clínica permanece; só o valor sai
        assert "reduz o tempo cirúrgico" in out
        assert "R$" not in out
        assert any(e.tipo == "alerta" for e in entries)

    def test_qualitative_cost_flagged_not_deleted(self):
        text = "A alternativa é economicamente inviável para o desfecho esperado."
        out, entries = _strip_fabricated_costs(text, evidences=[])
        assert "desfecho esperado" in out  # frase preservada
        assert any(e.tipo == "alerta" for e in entries)

    def test_legal_stripper_reports_removals(self):
        text = "A cobertura é obrigatória. Conforme a RN 465 da ANS, o rol é taxativo."
        out, entries = _strip_legal_from_body(text)
        assert "RN 465" not in out
        assert "cobertura é obrigatória" in out
        assert any(e.tipo == "remocao" for e in entries)


class TestPdfRendersSectionsAndFields:
    def test_pdf_generates_with_new_fields(self):
        body = _assemble_body(SECTIONS)
        pdf = generate_pdf_bytes(
            justificativa=body,
            paciente_nome="João Silva",
            cid="M17.1",
            diagnostico_resumo="Gonartrose",
            produto_nome="Synvisc-One",
            convenio="Bradesco",
            especialidade="Ortopedia",
            codigo_tuss="20104340",
            referencias=["Altman et al., 2015"],
            checklist={"diagnostico": True, "base_legal_ans": True},
            aprovado=True,
            base_legal="Conforme RN 424 da ANS.",
            medico_nome="Dra. Ana",
            medico_crm="CRM/SP 123456",
            medico_rqe="45678",
            clinica_nome="Clínica Exemplo",
            paciente_dob="1965-03-12",
            paciente_carteirinha="998877",
            guia_numero="G-1",
            cids_secundarios=["M25.5"],
            materiais_tuss=[{"codigo": "20104340", "nome": "Synvisc-One", "qtd": 1}],
            registro_anvisa="80145900123",
        )
        assert pdf[:5] == b"%PDF-"
        assert len(pdf) > 1500
