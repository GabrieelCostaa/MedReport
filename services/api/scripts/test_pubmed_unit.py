"""
Testes unitários do PubMed Service.
Testa ESearch, EFetch, cache e fallback sem chamar IA.
Uso: cd services/api && python scripts/test_pubmed_unit.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

from app.services.pubmed_service import (
    search_pubmed,
    fetch_articles,
    _cid_to_search_term,
    _parse_article,
    _cache_to_evidence_dicts,
)
from app.core.config import settings

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def report(name: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    results.append((name, ok))
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


async def test_search_pubmed():
    """ESearch deve retornar PMIDs válidos para CID conhecido."""
    print("\n=== test_search_pubmed ===")
    query = '"knee osteoarthritis" AND ("clinical trial"[pt] OR "review"[pt])'
    pmids = await search_pubmed(query, max_results=5)
    report("retorna lista", isinstance(pmids, list))
    report("retorna PMIDs", len(pmids) > 0, f"found {len(pmids)}")
    if pmids:
        report("PMIDs são numéricos", all(p.isdigit() for p in pmids))


async def test_fetch_articles():
    """EFetch deve parsear artigos com campos obrigatórios."""
    print("\n=== test_fetch_articles ===")
    pmids = await search_pubmed('"knee osteoarthritis" AND "meta-analysis"[pt]', max_results=3)
    if not pmids:
        report("ESearch retornou PMIDs para fetch", False, "sem PMIDs para testar")
        return

    articles = await fetch_articles(pmids)
    report("retorna artigos", len(articles) > 0, f"parsed {len(articles)}/{len(pmids)}")

    for art in articles:
        report(f"PMID {art['pmid']} tem título", bool(art.get("title")))
        report(f"PMID {art['pmid']} tem first_author", bool(art.get("first_author")))
        report(f"PMID {art['pmid']} tem year", bool(art.get("year")))
        report(
            f"PMID {art['pmid']} year válido",
            art.get("year", "").isdigit() and 1990 <= int(art["year"]) <= 2030,
            art.get("year", ""),
        )
        report(
            f"PMID {art['pmid']} first_author válido",
            len(art.get("first_author", "")) > 2 and not any(c.isdigit() for c in art["first_author"]),
            art.get("first_author", ""),
        )


async def test_cid_to_search_term():
    """Monta queries de busca corretas para diferentes CIDs."""
    print("\n=== test_cid_to_search_term ===")
    q1 = _cid_to_search_term("M17.0", "Kit EC2 Enxerto")
    report("M17.0 inclui knee osteoarthritis", "knee osteoarthritis" in q1.lower())
    report("M17.0 com produto inclui SVF/fat", "stromal vascular fraction" in q1.lower() or "fat grafting" in q1.lower())

    q2 = _cid_to_search_term("E88.2", "Kit FO Laser")
    report("E88.2 inclui lipedema", "lipedema" in q2.lower())
    report("E88.2 com laser inclui photobiomodulation", "laser" in q2.lower() or "photobiomodulation" in q2.lower())

    q3 = _cid_to_search_term("Z99.9")
    report("CID desconhecido gera query", len(q3) > 10, q3[:60])


async def test_cache_to_evidence_dicts():
    """Converte PubmedCache rows em dicts corretamente."""
    print("\n=== test_cache_to_evidence_dicts ===")

    class FakeRow:
        pmid = "12345678"
        snippet = "This is a test abstract about knee OA treatment."
        abstract = "This is a test abstract about knee OA treatment."
        title = "Test Article Title"
        authors = "Smith J, Doe A, Johnson B"
        first_author = "Smith"
        referencia_completa = "Smith J et al. Test Article. J Test. 2023."
        ano = "2023"
        year = "2023"
        tipo = "rct"
        article_type = "rct"
        journal = "Journal of Test"
        doi = "10.1234/test"

    rows = [FakeRow()]
    dicts = _cache_to_evidence_dicts(rows)

    report("retorna lista", isinstance(dicts, list) and len(dicts) == 1)
    d = dicts[0]
    report("tem source=pubmed", d.get("source") == "pubmed")
    report("tem pmid", d.get("pmid") == "12345678")
    report("tem autor", d.get("autor") == "Smith")
    report("tem ano", d.get("ano") == "2023")
    report("tem snippet", len(d.get("snippet", "")) > 0)


async def test_fallback_timeout():
    """Com timeout simulado, search_pubmed retorna lista vazia sem erro."""
    print("\n=== test_fallback_timeout ===")
    original = settings.PUBMED_TIMEOUT_SECONDS
    try:
        settings.PUBMED_TIMEOUT_SECONDS = 0.001
        pmids = await search_pubmed("knee osteoarthritis", max_results=5)
        report("retorna lista vazia sem crash", isinstance(pmids, list) and len(pmids) == 0)
    except Exception as e:
        report("não levanta exceção", False, str(e))
    finally:
        settings.PUBMED_TIMEOUT_SECONDS = original


async def test_kill_switch():
    """Com PUBMED_ENABLED=False, nenhuma chamada externa acontece."""
    print("\n=== test_kill_switch ===")
    original = settings.PUBMED_ENABLED
    try:
        settings.PUBMED_ENABLED = False
        from app.services.pubmed_service import get_evidences_for_cid

        with patch("app.services.pubmed_service.search_pubmed", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = ["12345"]
            result = await get_evidences_for_cid(None, "M17.0", "Kit EC2", "Gonartrose")
            report("retorna lista vazia", isinstance(result, list) and len(result) == 0)
            report("search_pubmed NÃO chamado", mock_search.call_count == 0, f"calls={mock_search.call_count}")
    finally:
        settings.PUBMED_ENABLED = original


async def main():
    print("=" * 60)
    print("TESTES UNITÁRIOS — PubMed Service")
    print("=" * 60)

    start = time.time()
    await test_cid_to_search_term()
    await test_cache_to_evidence_dicts()
    await test_search_pubmed()
    await test_fetch_articles()
    await test_fallback_timeout()
    await test_kill_switch()
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print(f"TOTAL: {passed} passed, {failed} failed ({elapsed:.1f}s)")
    if failed:
        print("\nFALHAS:")
        for name, ok in results:
            if not ok:
                print(f"  - {name}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
