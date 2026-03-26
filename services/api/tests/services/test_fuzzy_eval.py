"""Tests for fuzzy evaluation utilities."""
import pytest
from app.services.fuzzy_eval import (
    exact_match_anvisa, exact_match_cid, exact_match_tuss,
    fuzzy_match_diagnosis, fuzzy_match_justificativa,
    f1_references, f1_keywords, evaluate_report,
)


class TestExactMatch:
    def test_anvisa_match(self):
        assert exact_match_anvisa("80030810056", "80030810056")
        assert exact_match_anvisa("800.308.100.56", "80030810056")
        assert not exact_match_anvisa("80030810057", "80030810056")

    def test_cid_match(self):
        assert exact_match_cid("M17.0", "m17.0")
        assert exact_match_cid("M17", "M17")
        assert not exact_match_cid("M17.0", "M17.1")

    def test_tuss_match(self):
        assert exact_match_tuss("20104340", "20104340")
        assert exact_match_tuss("201.043.40", "20104340")
        assert not exact_match_tuss("20104341", "20104340")


class TestFuzzyDiagnosis:
    def test_paraphrased_diagnosis(self):
        r = fuzzy_match_diagnosis(
            "Gonartrose primária bilateral grau III",
            "Gonartrose bilateral, grau III de Kellgren-Lawrence",
        )
        assert r.passed, f"Score {r.score} too low"

    def test_unrelated_diagnosis(self):
        r = fuzzy_match_diagnosis(
            "Hérnia inguinal bilateral recidivante",
            "Gonartrose bilateral grau III",
        )
        assert not r.passed

    def test_same_text(self):
        r = fuzzy_match_diagnosis("Gonartrose M17.0", "Gonartrose M17.0")
        assert r.score == 100.0


class TestFuzzyJustificativa:
    def test_similar_texts(self):
        r = fuzzy_match_justificativa(
            "Paciente com gonartrose bilateral. Indica-se viscossuplementação com hialuronato.",
            "Paciente apresenta gonartrose bilateral. Indica-se viscossuplementação com ácido hialurônico.",
        )
        assert r.passed

    def test_completely_different(self):
        r = fuzzy_match_justificativa(
            "O sistema solar possui oito planetas.",
            "Paciente com gonartrose bilateral indica-se cirurgia.",
        )
        assert not r.passed


class TestF1References:
    def test_exact_refs(self):
        result = f1_references(
            ["Altman et al., 2015", "Bannuru et al., 2019"],
            ["Altman et al., 2015", "Bannuru et al., 2019"],
        )
        assert result.f1 == 1.0

    def test_fuzzy_ref_matching(self):
        result = f1_references(
            ["Altman RD et al. 2015", "Bannuru RR, et al., 2019"],
            ["Altman et al., 2015", "Bannuru et al., 2019"],
        )
        assert result.f1 >= 0.9

    def test_missing_refs(self):
        result = f1_references(
            ["Altman et al., 2015"],
            ["Altman et al., 2015", "Bannuru et al., 2019", "Dahl et al., 1985"],
        )
        assert result.recall < 0.5
        assert len(result.missing) == 2

    def test_extra_refs(self):
        result = f1_references(
            ["Altman 2015", "Bannuru 2019", "FakeAuthor 2023", "Invented 2024"],
            ["Altman 2015", "Bannuru 2019"],
        )
        assert result.recall == 1.0
        assert result.precision == 0.5

    def test_empty_expected(self):
        result = f1_references(["Altman 2015"], [])
        assert result.f1 == 1.0

    def test_empty_generated(self):
        result = f1_references([], ["Altman 2015"])
        assert result.f1 == 0.0


class TestF1Keywords:
    def test_all_found(self):
        r = f1_keywords(
            "Viscossuplementação com peso molecular 6.000 kDa",
            ["viscossuplementação", "6.000", "peso molecular"],
        )
        assert r.f1 == 1.0

    def test_partial_found(self):
        r = f1_keywords(
            "Tratamento articular com hialuronato",
            ["viscossuplementação", "6.000", "peso molecular"],
        )
        assert r.f1 == 0.0
        assert len(r.missing) == 3


class TestEvaluateReport:
    def test_perfect_report(self):
        golden = "Viscossuplementação com hialuronato 6.000 kDa para gonartrose M17.0"
        result = evaluate_report(
            generated_text=golden,
            golden_text=golden,
            generated_refs=["Altman et al., 2015"],
            expected_refs=["Altman et al., 2015"],
            expected_keywords=["viscossuplementação", "6.000"],
            generated_anvisa="80030810056",
            official_anvisa="80030810056",
            generated_cid="M17.0",
            expected_cid="M17.0",
        )
        assert result.passed
        assert result.overall_score > 0.9

    def test_wrong_anvisa_fails(self):
        result = evaluate_report(
            generated_text="Hialuronato 6.000 kDa",
            golden_text="Hialuronato 6.000 kDa",
            generated_refs=[], expected_refs=[],
            expected_keywords=["6.000"],
            generated_anvisa="80030810057",
            official_anvisa="80030810056",
        )
        assert not result.anvisa_match
