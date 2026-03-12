"""
Testes unitários para o parser de DUT (Anexo II).
Determinísticos — testa segmentação e validação sem rede/LLM.
"""
import pytest

from scripts.etl.parse_dut_pdf import (
    segment_dut_pdf,
    validate_structured_dut,
    build_dsl_from_structured,
    _extract_title,
    DUT_ANCHOR_RE,
)


MOCK_DUT_STRUCTURED = {
    "numero_dut": "10",
    "titulo": "Viscossuplementação",
    "criterios": [
        {
            "id": "A",
            "tipo": "deterministico",
            "campo_paciente": "idade",
            "operador": ">=",
            "valor": 18,
            "unidade": "anos",
            "descricao": "Idade >= 18 anos",
            "evidence_span": "pacientes com idade igual ou superior a 18 anos",
            "page_ref": 42,
        },
        {
            "id": "B",
            "tipo": "deterministico",
            "campo_paciente": "grau_kellgren_lawrence",
            "operador": "in",
            "valor": [2, 3],
            "descricao": "Gonartrose grau II ou III (Kellgren-Lawrence)",
            "evidence_span": "classificados como grau II ou III na escala de Kellgren-Lawrence",
            "page_ref": 42,
        },
        {
            "id": "C",
            "tipo": "deterministico",
            "campo_paciente": "tempo_tratamento_conservador_meses",
            "operador": ">=",
            "valor": 6,
            "unidade": "meses",
            "descricao": "Falha de tratamento conservador por >= 6 meses",
            "evidence_span": "após insucesso com tratamento conservador por pelo menos 6 meses",
            "page_ref": 43,
        },
        {
            "id": "D",
            "tipo": "subjetivo",
            "descricao": "Limitação funcional significativa documentada",
            "evidence_span": "com limitação funcional significativa",
            "page_ref": 43,
        },
    ],
    "exclusoes": [
        {
            "id": "EX1",
            "tipo": "exclusao",
            "descricao": "Exclui-se uso estético (Nota de Rodapé 3, p.42)",
            "evidence_span": "Nota: Exclui-se o uso para fins exclusivamente estéticos",
            "origem": "nota_rodape",
        },
    ],
    "exames_exigidos": ["Radiografia de joelho AP e perfil", "Escala de dor (VAS)"],
    "documentos_exigidos": ["Relatório de fisioterapia (mínimo 6 meses)"],
    "logica": "A AND B AND C AND NOT EX1",
}


MOCK_DUT_BARIATRICA = {
    "numero_dut": "27",
    "titulo": "Cirurgia Bariátrica",
    "criterios": [
        {
            "id": "A",
            "tipo": "deterministico",
            "campo_paciente": "imc",
            "operador": ">=",
            "valor": 40,
            "descricao": "IMC >= 40 kg/m2",
            "evidence_span": "IMC >= 40 kg/m²",
            "page_ref": 80,
        },
        {
            "id": "B",
            "tipo": "deterministico",
            "campo_paciente": "idade",
            "operador": "between",
            "valor": [18, 65],
            "descricao": "Idade entre 18 e 65 anos",
            "evidence_span": "pacientes entre 18 e 65 anos de idade",
            "page_ref": 80,
        },
    ],
    "exclusoes": [],
    "logica": "A AND B",
}


class TestDutAnchorRegex:
    def test_matches_standard(self):
        assert DUT_ANCHOR_RE.search("DUT nº 10 – Viscossuplementação")

    def test_matches_without_accent(self):
        assert DUT_ANCHOR_RE.search("DUT no 27")

    def test_matches_dotted(self):
        assert DUT_ANCHOR_RE.search("DUT n. 45.1")

    def test_matches_diretriz_full(self):
        assert DUT_ANCHOR_RE.search("Diretriz de Utilização nº 10")

    def test_extracts_number(self):
        m = DUT_ANCHOR_RE.search("DUT nº 10 – Viscossuplementação")
        assert m.group(1) == "10"


class TestExtractTitle:
    def test_extracts_from_first_line(self):
        lines = ["DUT nº 10 – Viscossuplementação Articular", "Critérios:"]
        title = _extract_title(lines)
        assert "Viscossuplementação" in title or len(title) > 5

    def test_empty_lines(self):
        assert _extract_title([]) == ""


class TestValidateStructuredDut:
    def test_valid_dut_no_warnings(self):
        warnings = validate_structured_dut(MOCK_DUT_STRUCTURED)
        assert len(warnings) == 0

    def test_missing_evidence_span(self):
        bad = {
            "criterios": [{"id": "A", "tipo": "deterministico", "campo_paciente": "idade"}],
            "logica": "A",
        }
        warnings = validate_structured_dut(bad)
        assert any("evidence_span" in w for w in warnings)

    def test_missing_campo_paciente(self):
        bad = {
            "criterios": [
                {"id": "A", "tipo": "deterministico", "evidence_span": "x", "operador": ">="}
            ],
            "logica": "A",
        }
        warnings = validate_structured_dut(bad)
        assert any("campo_paciente" in w for w in warnings)

    def test_missing_logica(self):
        bad = {"criterios": []}
        warnings = validate_structured_dut(bad)
        assert any("logica" in w.lower() for w in warnings)

    def test_error_response(self):
        warnings = validate_structured_dut({"error": "parse fail"})
        assert len(warnings) == 1

    def test_no_criteria_warning(self):
        warnings = validate_structured_dut({"criterios": [], "logica": "true"})
        assert any("Nenhum critério" in w for w in warnings)

    def test_exclusion_without_evidence(self):
        bad = {
            "criterios": [{"id": "A", "tipo": "subjetivo", "evidence_span": "x"}],
            "exclusoes": [{"id": "EX1"}],
            "logica": "A AND NOT EX1",
        }
        warnings = validate_structured_dut(bad)
        assert any("EX1" in w for w in warnings)


class TestBuildDsl:
    def test_builds_from_structured(self):
        dsl = build_dsl_from_structured(MOCK_DUT_STRUCTURED)
        assert "criterios" in dsl
        assert "exclusoes" in dsl
        assert "logica" in dsl

    def test_deterministic_criteria_have_fields(self):
        dsl = build_dsl_from_structured(MOCK_DUT_STRUCTURED)
        det = [c for c in dsl["criterios"] if c["tipo"] == "deterministico"]
        for c in det:
            assert "campo_paciente" in c
            assert "operador" in c
            assert "valor" in c

    def test_subjective_criteria_flagged(self):
        dsl = build_dsl_from_structured(MOCK_DUT_STRUCTURED)
        subj = [c for c in dsl["criterios"] if c["tipo"] == "subjetivo"]
        for c in subj:
            assert c.get("requer_llm") is True

    def test_exclusions_preserved(self):
        dsl = build_dsl_from_structured(MOCK_DUT_STRUCTURED)
        assert len(dsl["exclusoes"]) == 1
        assert dsl["exclusoes"][0]["origem"] == "nota_rodape"

    def test_bariatrica_dsl(self):
        dsl = build_dsl_from_structured(MOCK_DUT_BARIATRICA)
        assert len(dsl["criterios"]) == 2
        assert dsl["logica"] == "A AND B"
