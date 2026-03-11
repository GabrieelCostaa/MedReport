"""
Testes unitários para o Validador Hard-Coded (Camada 4).
Garante que dados técnicos inventados pela IA são detectados e bloqueados.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.services.agents.validator import (
    validate_technical_data,
    _normalize_number,
    _extract_all_entities,
    _check_viscosidade,
    _check_peso_molecular,
    _check_concentracao,
    _check_registro_anvisa,
    ValidationResult,
)
from tests.conftest import MockProduct, MockProductAdhesion


class TestNormalizeNumber:
    def test_integer(self):
        assert _normalize_number("6000") == 6000.0

    def test_decimal_dot(self):
        assert _normalize_number("6.5") == 6.5

    def test_decimal_comma_br(self):
        assert _normalize_number("6,5") == 6.5

    def test_thousands_dot_br(self):
        assert _normalize_number("80.000") == 80000.0

    def test_range_separator(self):
        assert _normalize_number("10.000") == 10000.0

    def test_empty(self):
        assert _normalize_number("abc") == 0.0


class TestEntityExtraction:
    def test_extracts_viscosity(self):
        text = "A viscosidade do produto é de 80.000 mPa.s, adequada para uso intra-articular."
        entities = _extract_all_entities(text)
        assert len(entities) >= 1
        assert any("mPa" in e.get("unidade", "") for e in entities)

    def test_extracts_molecular_weight(self):
        text = "Ácido hialurônico de alto peso molecular (6.000 kDa)."
        entities = _extract_all_entities(text)
        assert len(entities) >= 1
        assert any("kDa" in e.get("unidade", "") for e in entities)

    def test_extracts_concentration(self):
        text = "Concentração de 10 mg/mL de hialuronato de sódio."
        entities = _extract_all_entities(text)
        assert len(entities) >= 1
        assert any("mg/mL" in e.get("unidade", "") or "mg/ml" in e.get("unidade", "") for e in entities)

    def test_extracts_anvisa(self):
        text = "Registro ANVISA: 80117900YYY"
        entities = _extract_all_entities(text)
        assert len(entities) >= 1

    def test_no_entities(self):
        text = "Este é um texto sem dados técnicos numéricos específicos."
        entities = _extract_all_entities(text)
        assert len(entities) == 0


class TestViscosidadeValidation:
    def test_correct_viscosity_passes(self):
        text = "Viscosidade de 100.000 mPa.s conforme bula oficial."
        issues = _check_viscosidade(text, "80.000 - 120.000 mPa.s")
        assert len(issues) == 0

    def test_wrong_viscosity_detected(self):
        text = "Viscosidade de 500 mPa.s, indicada para uso articular."
        issues = _check_viscosidade(text, "80.000 - 120.000 mPa.s")
        assert len(issues) > 0
        assert issues[0].campo == "viscosidade"
        assert issues[0].severidade == "bloqueante"

    def test_na_viscosity_skipped(self):
        text = "Viscosidade de 500 mPa.s"
        issues = _check_viscosidade(text, "Não aplicável (dispositivo sólido)")
        assert len(issues) == 0

    def test_no_viscosity_in_text(self):
        text = "Produto indicado para cirurgias abdominais."
        issues = _check_viscosidade(text, "80.000 - 120.000 mPa.s")
        assert len(issues) == 0


class TestPesoMolecularValidation:
    def test_correct_weight_passes(self):
        text = "Alto peso molecular de 6.000 kDa proporciona permanência articular."
        issues = _check_peso_molecular(text, "6.000 kDa")
        assert len(issues) == 0

    def test_wrong_weight_detected(self):
        """TESTE DO AUDITOR: Se a IA inventar peso molecular, o validador DEVE bloquear."""
        text = "Peso molecular de 500 kDa confere propriedades viscoelásticas."
        issues = _check_peso_molecular(text, "6.000 kDa")
        assert len(issues) > 0
        assert issues[0].severidade == "bloqueante"
        assert issues[0].tipo == "discrepancia"

    def test_na_weight_skipped(self):
        text = "Peso molecular de 500 kDa"
        issues = _check_peso_molecular(text, "Não aplicável (barreira anti-aderência)")
        assert len(issues) == 0

    def test_weight_54_vs_6000(self):
        """Teste específico: Opus 2F tem 6.000 kDa, IA escreve 5.4 -> deve detectar."""
        text = "O produto possui peso molecular de 5.4 kDa."
        issues = _check_peso_molecular(text, "6.000 kDa")
        assert len(issues) > 0


class TestConcentracaoValidation:
    def test_correct_concentration(self):
        text = "Concentração de 10 mg/mL de hialuronato de sódio."
        issues = _check_concentracao(text, "10 mg/mL de hialuronato de sódio")
        assert len(issues) == 0

    def test_wrong_concentration(self):
        text = "Concentração de 25 mg/mL de ácido hialurônico."
        issues = _check_concentracao(text, "10 mg/mL de hialuronato de sódio")
        assert len(issues) > 0
        assert issues[0].severidade == "bloqueante"


class TestRegistroAnvisaValidation:
    def test_correct_anvisa(self):
        text = "Produto com registro ANVISA: 80117900YYY"
        issues = _check_registro_anvisa(text, "80117900YYY")
        assert len(issues) == 0

    def test_wrong_anvisa(self):
        text = "Registro ANVISA: 99999999ZZZ"
        issues = _check_registro_anvisa(text, "80117900YYY")
        assert len(issues) > 0
        assert issues[0].severidade == "bloqueante"


class TestFullValidation:
    def test_clean_text_passes(self):
        """Texto com dados corretos deve passar na validação."""
        product = MockProduct()
        text = (
            "Indica-se viscossuplementação com ácido hialurônico de alto peso molecular "
            "(6.000 kDa) e concentração de 10 mg/mL, com viscosidade de 100.000 mPa.s. "
            "Produto com registro ANVISA: 80117900YYY."
        )
        result = validate_technical_data(text, product)
        assert result.aprovado is True
        assert not result.has_blocking_issues
        assert len(result.entities_found) >= 3

    def test_hallucinated_data_blocked(self):
        """Texto com dados inventados pela IA DEVE ser bloqueado."""
        product = MockProduct()
        text = (
            "Indica-se viscossuplementação com ácido hialurônico de peso molecular "
            "de 500 kDa e concentração de 50 mg/mL, viscosidade de 200 mPa.s. "
            "Registro ANVISA: 99999999ZZZ."
        )
        result = validate_technical_data(text, product)
        assert result.aprovado is False
        assert result.has_blocking_issues
        assert len(result.issues) >= 2

    def test_text_without_technical_data(self):
        """Texto narrativo sem dados numéricos deve passar (sem o que validar)."""
        product = MockProduct()
        text = (
            "O paciente apresenta quadro clínico de osteoartrite de joelho com "
            "limitação funcional significativa. Indica-se tratamento específico."
        )
        result = validate_technical_data(text, product)
        assert result.aprovado is True

    def test_adhesion_product_validation(self):
        """Adhesion STP+ com 'Não aplicável' no peso molecular não deve gerar falso positivo."""
        product = MockProductAdhesion()
        text = (
            "Barreira anti-aderência com viscosidade de 15.000 mPa.s. "
            "Registro ANVISA: 80117900XXX."
        )
        result = validate_technical_data(text, product)
        assert result.aprovado is True

    def test_mixed_correct_and_wrong(self):
        """Se um dado está correto e outro errado, deve detectar o errado."""
        product = MockProduct()
        text = (
            "Ácido hialurônico de 6.000 kDa mas com viscosidade de 5 mPa.s."
        )
        result = validate_technical_data(text, product)
        assert result.aprovado is False
        blocking = [i for i in result.issues if i.severidade == "bloqueante"]
        assert any(i.campo == "viscosidade" for i in blocking)
