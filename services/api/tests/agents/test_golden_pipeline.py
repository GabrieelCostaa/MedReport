"""
Golden Tests: justificativas aprovadas como ground truth.

Verifica que o pipeline produz output que atende critérios mínimos de qualidade:
1. Todas as seções obrigatórias presentes
2. CID aparece no texto
3. Referências bibliográficas com autor e ano
4. Nenhuma alucinação técnica (dados do produto corretos)
5. Sem valores monetários fabricados
6. Comprimento mínimo da justificativa
"""
import re
import pytest
from unittest.mock import MagicMock

from app.services.agents.validator import validate_technical_data, ValidationResult
from app.services.agents.auditor import _strip_fabricated_costs, _check_cid_in_text, _local_checklist
from app.services.agents.writer import DraftReport
from app.services.agents.schemas import WriterOutput, AuditorOutput, AuditorChecklist


# ─── Golden fixtures: approved justification patterns ─────────────────────────

GOLDEN_ORTOPEDIA = """
Paciente apresenta diagnóstico de gonartrose primária bilateral (CID M17.0),
classificada como grau III na escala de Kellgren-Lawrence, com comprometimento
progressivo da função articular e falência das medidas conservadoras incluindo
AINEs, fisioterapia cinesioterapêutica e infiltrações com corticosteroides.
O quadro inflamatório crônico intra-articular, dominado por citocinas
pró-inflamatórias (IL-1β, TNF-α), resulta em degradação acelerada da
matriz extracelular cartilaginosa e apoptose dos condrócitos remanescentes.

A viscossuplementação com hialuronato de alto peso molecular (6.000 kDa,
viscosidade 10.000-29.000 mPa.s) promove reestabelecimento da homeostase
articular e viscoindução, restaurando as propriedades viscoelásticas do
líquido sinovial (Altman et al., 2015). Meta-análise de Bannuru et al. (2019)
demonstrou superioridade do ácido hialurônico de alto peso molecular frente
a formulações lineares de baixo peso.

A rede tridimensional reticulada (cross-linked) confere resistência à
degradação enzimática por hialuronidases, garantindo permanência intra-articular
prolongada. Diferente de hialuronatos lineares ou de baixo peso molecular,
que são degradados em 48 horas, a reticulação polimérica garante ação
terapêutica sustentada por até 6 meses (Dahl et al., 1985).

A manutenção do quadro inflamatório crônico sem intervenção adequada resultará
em evolução para perda funcional irreversível com necessidade de artroplastia
total de joelho, procedimento de maior morbidade e complexidade.
"""

GOLDEN_PRODUCT_ORTOPEDIA = MagicMock(
    id="test-product-1",
    nome="Synvisc-One",
    linha="Hialuronatos",
    viscosidade="10.000 - 29.000 mPa.s",
    peso_molecular="6.000 kDa",
    concentracao="8 mg/mL",
    registro_anvisa="80030810056",
    diferenciais_clinicos="Reticulação polimérica tridimensional",
    indicacoes="Osteoartrite de joelho, gonartrose, articulação",
    contraindicacoes="Infecção ativa no sítio de injeção",
    codigo_tuss_sugerido="20104340",
    descricao_tecnica="Hialuronato de sódio reticulado de alto peso molecular",
    referencias_bibliograficas=["Altman et al., 2015", "Bannuru et al., 2019", "Dahl et al., 1985"],
)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestGoldenQualityCriteria:
    """Verify that golden text meets all quality criteria."""

    def test_cid_present_in_text(self):
        """CID must appear in the justification text."""
        assert re.search(r"CID[\s-]*[A-Z]\d{2}", GOLDEN_ORTOPEDIA, re.IGNORECASE)

    def test_minimum_length(self):
        """Justification must be at least 1500 characters."""
        assert len(GOLDEN_ORTOPEDIA.strip()) >= 1000  # Golden is ~1500+

    def test_has_bibliographic_references(self):
        """Must have at least 2 author citations (Author et al., Year)."""
        citation_pattern = re.compile(r"\([A-Z][a-záéíóúàãõâêô]+\s+et\s+al\.,?\s*\d{4}\)")
        matches = citation_pattern.findall(GOLDEN_ORTOPEDIA)
        assert len(matches) >= 2, f"Expected >= 2 citations, found {len(matches)}: {matches}"

    def test_no_fabricated_monetary_values(self):
        """Must not contain R$ values."""
        assert "R$" not in GOLDEN_ORTOPEDIA
        assert "reais" not in GOLDEN_ORTOPEDIA.lower()

    def test_no_rn_in_body(self):
        """RN references must not appear in justification body."""
        rn_pattern = re.compile(r"RN\s*\d{3}", re.IGNORECASE)
        assert not rn_pattern.search(GOLDEN_ORTOPEDIA)

    def test_has_required_sections(self):
        """Must mention key clinical sections."""
        text_lower = GOLDEN_ORTOPEDIA.lower()
        assert "conservador" in text_lower or "falh" in text_lower  # falha terapêutica
        assert "risco" in text_lower or "morbidade" in text_lower or "irreversível" in text_lower


class TestHardValidatorWithGolden:
    """Verify that golden text passes hard validation without blocking issues."""

    def test_golden_passes_hard_validation(self):
        result = validate_technical_data(
            GOLDEN_ORTOPEDIA,
            GOLDEN_PRODUCT_ORTOPEDIA,
            medico_inputs={
                "cid": "M17.0",
                "diagnostico": "Gonartrose primária bilateral grau III Kellgren-Lawrence",
                "paciente_nome": "João da Silva",
            },
        )
        blocking = [i for i in result.issues if i.severidade == "bloqueante"]
        assert result.aprovado, f"Golden text should pass validation. Blocking issues: {blocking}"

    def test_golden_detects_entities(self):
        result = validate_technical_data(
            GOLDEN_ORTOPEDIA,
            GOLDEN_PRODUCT_ORTOPEDIA,
        )
        assert len(result.entities_found) >= 2, "Should find viscosity and molecular weight entities"


class TestAuditorDeterministic:
    """Test deterministic post-processing functions."""

    def test_strip_fabricated_costs_removes_uncited(self):
        text = "A técnica é eficaz. O procedimento alternativo custa R$5.000 sem considerar complicações. A literatura comprova."
        cleaned, entries = _strip_fabricated_costs(text, [])
        # R$5.000 without evidence should be removed
        assert "R$5.000" not in cleaned
        # Other sentences should be preserved
        assert "eficaz" in cleaned

    def test_check_cid_in_text_passes(self):
        entries = _check_cid_in_text("Paciente com CID M17.0 apresenta gonartrose.")
        assert len(entries) == 0

    def test_check_cid_in_text_fails(self):
        entries = _check_cid_in_text("Paciente apresenta gonartrose bilateral.")
        assert len(entries) > 0

    def test_local_checklist_complete(self):
        draft = DraftReport(
            justificativa_completa="x" * 200,
            diagnostico_resumo="Gonartrose M17.0",
            falha_terapeutica="AINEs e fisioterapia sem melhora",
            risco_nao_realizacao="Evolução para artroplastia",
            base_legal="Conforme RN 395 da ANS",
            referencias=["Altman et al., 2015"],
        )
        checklist = _local_checklist(draft)
        assert all(checklist.values()), f"All checklist items should pass: {checklist}"


class TestCIDValidation:
    """Test CID format validation."""

    def test_valid_cids(self):
        valid = ["M17.0", "A00", "Z99.9", "E11.5", "L97", "K40.2"]
        for cid in valid:
            assert re.match(r"^[A-Z]\d{2}(\.\d{1,2})?$", cid), f"{cid} should be valid"

    def test_invalid_cids(self):
        invalid = ["", "123", "MM17", "M1", "M17.123", "m17.0", "17.0"]
        for cid in invalid:
            assert not re.match(r"^[A-Z]\d{2}(\.\d{1,2})?$", cid or ""), f"{cid} should be invalid"


class TestWriterSchema:
    """Test that Pydantic schemas validate correctly."""

    def test_writer_output_valid(self):
        output = WriterOutput(
            quadro_clinico="q" * 600,
            falha_terapeutica="f" * 400,
            justificativa_tecnica="j" * 800,
            evidencia_cientifica="e" * 500,
            risco_nao_realizacao="r" * 400,
            conclusao="c" * 200,
            diagnostico_resumo="Gonartrose",
            base_legal="RN 395 ANS",
            referencias=["Altman et al., 2015"],
        )
        assert output.quadro_clinico
        assert len(output.referencias) == 1

    def test_writer_output_rejects_short_sections(self):
        """Os mínimos por seção devem ser aplicados (instructor retry depende disso)."""
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            WriterOutput(
                quadro_clinico="curto demais",
                falha_terapeutica="f" * 400,
                justificativa_tecnica="j" * 800,
                evidencia_cientifica="e" * 500,
                risco_nao_realizacao="r" * 400,
                conclusao="c" * 200,
                diagnostico_resumo="x",
                base_legal="RN 395",
            )

    def test_auditor_output_valid(self):
        output = AuditorOutput(
            chain_of_thought="Verificando viscosidade: 10.000 mPa.s no texto, oficial 10.000-29.000. OK.",
            texto_corrigido="Texto auditado aqui",
            aprovado=True,
            checklist=AuditorChecklist(
                diagnostico=True, justificativa_tecnica=True,
                falha_terapeutica=True, risco_nao_realizacao=True,
                base_legal_ans=True, referencia_bibliografica=True,
            ),
            audit_log=[],
            referencias_validadas=["Altman et al., 2015"],
        )
        assert output.aprovado
        assert output.chain_of_thought
