"""Métricas de qualidade: citação determinística + fail-soft do juiz LLM."""
import pytest

from app.services.quality_metrics import (
    QualityScores,
    citation_accuracy_deterministic,
    compute_quality_metrics,
)

PUBMED = [
    {"autor": "Teixeira", "ano": "2021", "snippet": "SVF evitou amputações"},
    {"autor": "Sadri", "ano": "2023", "snippet": "melhora funcional WOMAC"},
]


class TestCitationAccuracy:
    def test_exact_match_scores_full(self):
        texto = "O SVF evitou amputações em 71% (Teixeira et al., 2021)."
        score, details = citation_accuracy_deterministic(texto, [], PUBMED)
        assert score == 1.0
        assert details["exatas"] == 1

    def test_fabricated_author_scores_zero(self):
        """O buraco da CLASSIC_AUTHORS: autor plausível colado numa frase inventada."""
        texto = "Estudos comprovam 90% de sucesso (Altman et al., 2015)."
        score, details = citation_accuracy_deterministic(texto, [], PUBMED)
        assert score == 0.0
        assert "altman 2015" in details["nao_encontradas"]

    def test_wrong_year_scores_half(self):
        texto = "O SVF evitou amputações (Teixeira et al., 2019)."
        score, details = citation_accuracy_deterministic(texto, [], PUBMED)
        assert score == 0.5
        assert "teixeira 2019" in details["ano_divergente"]

    def test_mixed_citations(self):
        texto = (
            "Melhora do WOMAC (Sadri et al., 2023). "
            "Eficácia comprovada (Fulano et al., 2020)."
        )
        score, _ = citation_accuracy_deterministic(texto, [], PUBMED)
        assert score == 0.5  # 1 exata de 2 citações

    def test_no_citations_returns_none(self):
        score, details = citation_accuracy_deterministic("Texto sem citações.", [], PUBMED)
        assert score is None
        assert details["citacoes_no_texto"] == 0

    def test_clinical_evidences_also_count(self):
        clinical = [{"autor": "Becker", "ano": "2018", "snippet": "..."}]
        texto = "Barreira eficaz (Becker et al., 2018)."
        score, _ = citation_accuracy_deterministic(texto, clinical, [])
        assert score == 1.0

    def test_product_and_researcher_refs_are_legitimate(self):
        """Regra #11 permite citar a ficha do produto e as evidências do
        Pesquisador — o medidor não pode punir essas citações (era o artefato
        que derrubou 'citação' no primeiro smoke test)."""
        extra = [
            "Altman RD, et al. Semin Arthritis Rheum. 2015;45(2):140-9.",
            "Bannuru RR, et al. Osteoarthritis Cartilage. 2019.",
        ]
        texto = (
            "Eficácia demonstrada (Altman et al., 2015). "
            "Diretriz recomenda o uso (Bannuru et al., 2019)."
        )
        score, details = citation_accuracy_deterministic(texto, [], PUBMED, extra)
        assert score == 1.0
        assert details["exatas"] == 2

    def test_extra_refs_do_not_whitelist_wrong_years(self):
        extra = ["Altman RD, et al. Semin Arthritis Rheum. 2015;45(2):140-9."]
        texto = "Eficácia comprovada (Altman et al., 1999)."
        score, details = citation_accuracy_deterministic(texto, [], [], extra)
        assert score == 0.5  # autor real, ano que não consta em nenhuma fonte
        assert "altman 1999" in details["ano_divergente"]


class TestQualityScores:
    def test_mean_ignores_none(self):
        s = QualityScores(faithfulness=0.8, relevancy=None, citation=0.6)
        assert s.mean() == 0.7

    def test_mean_all_none(self):
        assert QualityScores().mean() is None

    def test_to_dict_shape(self):
        d = QualityScores(faithfulness=0.9).to_dict()
        assert d["faithfulness"] == 0.9
        assert "media" in d and "details" in d


class TestFailSoft:
    @pytest.mark.asyncio
    async def test_no_api_key_still_returns_deterministic(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
        texto = "Melhora do WOMAC (Sadri et al., 2023)."
        scores = await compute_quality_metrics(
            texto, cid="M17.1", diagnostico="gonartrose",
            product_name="Kit", pubmed_evidences=PUBMED,
            faithfulness_score=0.85,
        )
        assert scores.citation == 1.0  # determinístico roda sem chave
        assert scores.faithfulness == 0.85  # repassado, não recalculado
        assert scores.relevancy is None  # juiz não rodou

    @pytest.mark.asyncio
    async def test_judge_error_never_raises(self, monkeypatch):
        from app.core.config import settings
        monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-fake")
        import openai

        class _Boom:
            def __init__(self, **kw):
                raise RuntimeError("boom")

        monkeypatch.setattr(openai, "AsyncOpenAI", _Boom)
        scores = await compute_quality_metrics(
            "Texto.", cid="M17.1", diagnostico="x", product_name="y",
        )
        assert scores.relevancy is None
