"""Qualidade da evidência: rerank léxico (rapidfuzz) + resolução CID→MeSH com cache
+ conector Europe PMC PT (query, parsing, filtro de relevância)."""
import pytest

from app.services.semantic_search import lexical_rerank
from app.services.pubmed_service import (
    _build_europepmc_pt_query, _europe_pmc_articles_to_evidence, _strip_html,
)


class TestLexicalRerank:
    def test_relevant_first(self):
        evs = [
            {"snippet": "cardiology trial about atrial fibrillation", "titulo": "X"},
            {"snippet": "viscosupplementation hyaluronic acid knee osteoarthritis", "titulo": "Altman"},
            {"snippet": "knee osteoarthritis WOMAC functional outcomes", "titulo": "Bannuru"},
        ]
        out = lexical_rerank("knee osteoarthritis viscosupplementation", evs, top_k=3)
        assert out[0]["titulo"] == "Altman"
        assert out[-1]["titulo"] == "X"
        assert all("rerank_score" in e for e in out)

    def test_empty_and_topk(self):
        assert lexical_rerank("q", []) == []
        evs = [{"snippet": f"t{i}"} for i in range(5)]
        assert len(lexical_rerank("q", evs, top_k=2)) == 2


class TestResolveCidTerms:
    async def test_dict_hit_no_llm(self, monkeypatch):
        import app.services.pubmed_service as ps
        calls = {"n": 0}

        async def _never(*a, **k):
            calls["n"] += 1
            return None
        monkeypatch.setattr(ps, "_llm_cid_to_mesh", _never)
        desc, mesh = await ps._resolve_cid_terms(None, "M17.0", "gonartrose")
        assert "osteoarthritis" in desc.lower()
        assert calls["n"] == 0  # CID no dict → não chama LLM

    async def test_llm_translation_is_cached(self, monkeypatch):
        """Cauda longa: 1ª chamada usa LLM e persiste; 2ª usa cache (sem LLM)."""
        import app.services.pubmed_service as ps
        from app.db.session import engine, Base, AsyncSessionLocal
        import app.db.models  # noqa

        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)

        calls = {"n": 0}

        async def _fake_llm(cid, diag):
            calls["n"] += 1
            return ("Heart Failure", '"Heart Failure"[mh]')
        monkeypatch.setattr(ps, "_llm_cid_to_mesh", _fake_llm)

        async with AsyncSessionLocal() as db:
            d1, m1 = await ps._resolve_cid_terms(db, "I50.0", "insuficiência cardíaca")
            assert m1 == '"Heart Failure"[mh]'
            assert calls["n"] == 1
        async with AsyncSessionLocal() as db:
            d2, m2 = await ps._resolve_cid_terms(db, "I50.0", "insuficiência cardíaca")
            assert m2 == '"Heart Failure"[mh]'
            assert calls["n"] == 1  # veio do cache MedicalConcept

        async with engine.begin() as c:
            await c.run_sync(Base.metadata.drop_all)

    async def test_fallback_when_llm_none(self, monkeypatch):
        import app.services.pubmed_service as ps

        async def _none(cid, diag):
            return None
        monkeypatch.setattr(ps, "_llm_cid_to_mesh", _none)
        desc, mesh = await ps._resolve_cid_terms(None, "Z99.9", "condição rara qualquer")
        assert desc and mesh  # heurístico não quebra
        assert "[tiab]" in mesh


class TestEuropePmcPt:
    def test_pt_query_is_portuguese_with_lang_filter(self):
        q_and = _build_europepmc_pt_query("Gonartrose primária bilateral grau III", "M17.0", "AND")
        assert "gonartrose" in q_and.lower()
        assert "LANG:por" in q_and and "LANG:spa" in q_and
        assert "primaria" not in q_and.lower()  # qualificador removido

    def test_strip_html(self):
        assert _strip_html("<h4>Objetivo</h4> avaliar <b>eficácia</b>") == "Objetivo avaliar eficácia"

    def test_articles_to_evidence_schema_and_source(self):
        raw = [{
            "pmid": "12345678", "title": "Tratamento da gonartrose",
            "authors": "Silva JA, Souza MB", "first_author": "Silva",
            "year": "2020", "journal": "Rev Bras Ortop",
            "abstract": "<p>Estudo sobre viscossuplementação</p>",
            "article_type": "rct", "doi": "10.1/x",
        }]
        evs = _europe_pmc_articles_to_evidence(raw, source="europepmc_pt")
        assert evs[0]["source"] == "europepmc_pt"
        assert evs[0]["autor"] == "Silva"
        assert "<p>" not in evs[0]["snippet"]  # HTML limpo
        assert set(evs[0]).issuperset({"pmid", "snippet", "autor", "ano", "tipo", "journal", "doi"})

    async def test_relevance_filter_keeps_only_relevant(self, monkeypatch):
        import app.services.pubmed_service as ps
        evs = [
            {"snippet": "gonartrose tratamento"},      # 0 relevante
            {"snippet": "gastrectomia oncológica"},    # 1 tangencial
        ]

        class _Msg:  # mock da resposta OpenAI
            content = '{"relevantes": [0]}'
        class _Choice: message = _Msg()
        class _Resp: choices = [_Choice()]

        class _Chat:
            class completions:
                @staticmethod
                async def create(**kw): return _Resp()
        class _Client:
            chat = _Chat()

        import openai
        monkeypatch.setattr(ps.settings, "OPENAI_API_KEY", "sk-test", raising=False)
        monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: _Client())
        out = await ps._llm_filter_relevant_pt("gonartrose", evs)
        assert len(out) == 1 and out[0]["snippet"] == "gonartrose tratamento"

    async def test_relevance_filter_failsoft_without_key(self, monkeypatch):
        import app.services.pubmed_service as ps
        monkeypatch.setattr(ps.settings, "OPENAI_API_KEY", "", raising=False)
        evs = [{"snippet": "a"}, {"snippet": "b"}]
        assert await ps._llm_filter_relevant_pt("x", evs) == evs  # sem chave → não filtra
