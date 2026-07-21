"""Qualidade da evidência: rerank léxico (rapidfuzz) + resolução CID→MeSH com cache."""
import pytest

from app.services.semantic_search import lexical_rerank


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
