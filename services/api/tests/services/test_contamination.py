"""Tests for contamination detector."""
import pytest
from unittest.mock import MagicMock
from app.services.contamination_detector import (
    check_contamination,
    detect_language_contamination,
    detect_training_leakage,
    check_cross_product_contamination,
    build_fingerprint,
)


def _make_product(name, anvisa, **kwargs):
    p = MagicMock()
    p.id = name.lower().replace(" ", "-")
    p.nome = name
    p.registro_anvisa = anvisa
    p.peso_molecular = kwargs.get("peso_molecular", "")
    p.viscosidade = kwargs.get("viscosidade", "")
    p.concentracao = kwargs.get("concentracao", "")
    p.diferenciais_clinicos = kwargs.get("diferenciais", "")
    return p


class TestCrossProductContamination:
    def test_clean_text(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Viscossuplementação com Synvisc-One. ANVISA 80030810056."
        fp_current = build_fingerprint(synvisc)
        fp_all = [build_fingerprint(synvisc), build_fingerprint(seprafilm)]
        issues = check_cross_product_contamination(text, fp_current, fp_all)
        assert len(issues) == 0

    def test_wrong_product_name(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Indica-se Seprafilm para viscossuplementação articular."
        fp_current = build_fingerprint(synvisc)
        fp_all = [build_fingerprint(synvisc), build_fingerprint(seprafilm)]
        issues = check_cross_product_contamination(text, fp_current, fp_all)
        blocking = [i for i in issues if i.severidade == "bloqueante"]
        assert len(blocking) >= 1

    def test_wrong_anvisa(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Registro ANVISA 80030810099 do produto articular."
        fp_current = build_fingerprint(synvisc)
        fp_all = [build_fingerprint(synvisc), build_fingerprint(seprafilm)]
        issues = check_cross_product_contamination(text, fp_current, fp_all)
        assert any(i.tipo == "fingerprint" for i in issues)


class TestLanguageContamination:
    def test_clean_portuguese(self):
        text = "Paciente apresenta diagnóstico de gonartrose bilateral."
        issues = detect_language_contamination(text)
        assert len(issues) == 0

    def test_english_phrase_detected(self):
        text = "The patient presents with bilateral knee osteoarthritis and furthermore needs surgery."
        issues = detect_language_contamination(text)
        assert any(i.tipo == "language" for i in issues)

    def test_acceptable_english_terms(self):
        text = "Estudo follow-up de 12 meses demonstrou que o scaffold cross-linked manteve integridade in vivo."
        issues = detect_language_contamination(text)
        # Regex-based issues only (acceptable terms should not trigger)
        blocking = [i for i in issues if i.severidade == "bloqueante"]
        assert len(blocking) == 0


class TestTrainingLeakage:
    def test_ai_disclosure(self):
        text = "As an AI language model, I cannot provide medical advice."
        issues = detect_training_leakage(text)
        assert any(i.severidade == "bloqueante" for i in issues)

    def test_model_name_leak(self):
        text = "Conforme recomendação do ChatGPT, o tratamento indicado é..."
        issues = detect_training_leakage(text)
        assert any(i.tipo == "training_leak" for i in issues)

    def test_clean_medical_text(self):
        text = "Conforme meta-análise de Altman et al. (2015), a viscossuplementação demonstrou superioridade."
        issues = detect_training_leakage(text)
        assert len(issues) == 0


class TestFullContaminationCheck:
    def test_full_clean_report(self):
        product = _make_product("Synvisc-One", "80030810056")
        text = "Paciente com gonartrose CID M17.0. Indica-se Synvisc-One. ANVISA 80030810056."
        result = check_contamination(text, product)
        assert result.clean

    def test_full_contaminated_report(self):
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = (
            "Indica-se Seprafilm para o joelho. "
            "The patient should receive treatment. "
            "As an AI model, recomendo este produto."
        )
        result = check_contamination(text, synvisc, [synvisc, seprafilm])
        assert not result.clean
        assert len(result.issues) >= 2  # cross-product + training leak

    def test_all_products_enables_cross_product_detection(self):
        """Regressão: sem all_products a detecção cross-produto fica desligada;
        com all_products (caminho novo do pipeline) ela é ativada."""
        synvisc = _make_product("Synvisc-One", "80030810056")
        seprafilm = _make_product("Seprafilm", "80030810099")
        text = "Indica-se Seprafilm para viscossuplementação do joelho."

        sem = check_contamination(text, synvisc)  # all_products=None
        com = check_contamination(text, synvisc, [synvisc, seprafilm])

        _cross = {"cross_product", "fingerprint"}
        cross_sem = [i for i in sem.issues if i.tipo in _cross]
        cross_com = [i for i in com.issues if i.tipo in _cross]
        assert len(cross_sem) == 0
        assert len(cross_com) >= 1
