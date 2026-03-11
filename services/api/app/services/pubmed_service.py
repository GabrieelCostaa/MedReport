"""
Serviço de integração com PubMed E-utilities (NCBI).
Busca artigos científicos e mantém cache progressivo no Postgres.
"""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import PubmedCache

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

CID_DESCRIPTIONS = {
    "E88.2": "lipedema",
    "M17.0": "knee osteoarthritis",
    "M17.1": "knee osteoarthritis",
    "M17.9": "knee osteoarthritis",
    "M16.0": "hip osteoarthritis",
    "M16.1": "hip osteoarthritis",
    "M16.9": "hip osteoarthritis",
    "N60.9": "breast reconstruction fat grafting",
    "E11.5": "diabetic foot ulcer",
    "L97": "chronic venous ulcer lower extremity",
    "G62.9": "peripheral neuropathy",
    "M79.1": "myalgia chronic pain",
    "L90.5": "skin atrophy lipoatrophy",
    "S83.5": "anterior cruciate ligament ACL",
    "K56.5": "intestinal adhesions",
    "M75.1": "rotator cuff syndrome shoulder",
    "I83.0": "varicose veins lower extremities",
    "C50.9": "breast neoplasm",
    "M54.5": "low back pain",
    "K43.9": "incisional hernia",
}


def _cid_to_search_term(cid: str, product_name: str = "", diagnostico: str = "") -> str:
    cid_upper = cid.strip().upper()
    desc = CID_DESCRIPTIONS.get(cid_upper, "")

    if not desc and diagnostico:
        desc = diagnostico[:80]

    product_terms = ""
    if product_name:
        clean = product_name.lower()
        if "laser" in clean:
            product_terms = "laser therapy OR photobiomodulation"
        elif "enxerto" in clean or "svf" in clean or "ec2" in clean:
            product_terms = "stromal vascular fraction OR fat grafting OR lipotransfer"
        elif "opus" in clean or "hialurônico" in clean or "hialuronico" in clean:
            product_terms = "hyaluronic acid viscosupplementation"
        elif "adhesion" in clean or "aderência" in clean:
            product_terms = "adhesion barrier prevention"
        elif "parafuso" in clean or "bioabsorv" in clean:
            product_terms = "bioabsorbable interference screw"
        elif "tela" in clean or "polipropileno" in clean or "mesh" in clean:
            product_terms = "polypropylene mesh hernia repair"
        elif "lipedema" in clean or "lp-ct" in clean:
            product_terms = "lipedema liposuction treatment"

    if desc and product_terms:
        return f'("{desc}") AND ({product_terms}) AND ("clinical trial"[pt] OR "meta-analysis"[pt] OR "review"[pt])'
    elif desc:
        return f'("{desc}") AND ("clinical trial"[pt] OR "meta-analysis"[pt] OR "review"[pt])'
    elif product_terms:
        return f'({product_terms}) AND ("clinical trial"[pt] OR "meta-analysis"[pt] OR "review"[pt])'
    else:
        return f'"{cid_upper}" AND ("clinical trial"[pt] OR "review"[pt])'


async def search_pubmed(query: str, max_results: int = 10) -> list[str]:
    """Chama ESearch e retorna lista de PMIDs."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "sort": "relevance",
        "retmode": "xml",
    }
    if settings.PUBMED_API_KEY:
        params["api_key"] = settings.PUBMED_API_KEY

    try:
        async with httpx.AsyncClient(timeout=settings.PUBMED_TIMEOUT_SECONDS) as client:
            resp = await client.get(ESEARCH_URL, params=params)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        pmids = [id_elem.text for id_elem in root.findall(".//IdList/Id") if id_elem.text]
        logger.info("PubMed ESearch: query=%s, found=%d PMIDs", query[:80], len(pmids))
        return pmids

    except Exception as e:
        logger.warning("PubMed ESearch failed: %s", e)
        return []


def _parse_article(article_elem) -> Optional[dict]:
    """Parseia um <PubmedArticle> XML em dict."""
    try:
        medline = article_elem.find(".//MedlineCitation")
        if medline is None:
            return None

        pmid_elem = medline.find("PMID")
        pmid = pmid_elem.text if pmid_elem is not None else ""

        article = medline.find("Article")
        if article is None:
            return None

        title_elem = article.find("ArticleTitle")
        title = title_elem.text if title_elem is not None else ""

        abstract_parts = []
        abstract_elem = article.find("Abstract")
        if abstract_elem is not None:
            for at in abstract_elem.findall("AbstractText"):
                label = at.get("Label", "")
                text = at.text or ""
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        author_list = article.find("AuthorList")
        authors = []
        first_author = ""
        if author_list is not None:
            for author in author_list.findall("Author"):
                last = author.find("LastName")
                init = author.find("Initials")
                if last is not None and last.text:
                    name = last.text
                    if init is not None and init.text:
                        name += f" {init.text}"
                    authors.append(name)
                    if not first_author:
                        first_author = last.text

        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else ""
        if not journal:
            j_abbrev = article.find(".//Journal/ISOAbbreviation")
            journal = j_abbrev.text if j_abbrev is not None else ""

        year = ""
        pub_date = article.find(".//Journal/JournalIssue/PubDate")
        if pub_date is not None:
            year_elem = pub_date.find("Year")
            if year_elem is not None:
                year = year_elem.text or ""
            if not year:
                medline_date = pub_date.find("MedlineDate")
                if medline_date is not None and medline_date.text:
                    year = medline_date.text[:4]

        doi = ""
        for eid in article.findall(".//ELocationID"):
            if eid.get("EIdType") == "doi":
                doi = eid.text or ""
                break

        pub_types = []
        for pt in article.findall(".//PublicationTypeList/PublicationType"):
            if pt.text:
                pub_types.append(pt.text.lower())

        article_type = "article"
        if any("meta-analysis" in t for t in pub_types):
            article_type = "meta-analysis"
        elif any("randomized" in t or "clinical trial" in t for t in pub_types):
            article_type = "rct"
        elif any("review" in t for t in pub_types):
            article_type = "review"
        elif any("case report" in t for t in pub_types):
            article_type = "case-report"

        return {
            "pmid": pmid,
            "title": title,
            "authors": ", ".join(authors),
            "first_author": first_author,
            "year": year,
            "journal": journal,
            "abstract": abstract,
            "article_type": article_type,
            "doi": doi,
        }
    except Exception as e:
        logger.warning("Failed to parse PubMed article: %s", e)
        return None


async def fetch_articles(pmids: list[str]) -> list[dict]:
    """Chama EFetch para obter detalhes dos artigos."""
    if not pmids:
        return []

    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "xml",
        "retmode": "xml",
    }
    if settings.PUBMED_API_KEY:
        params["api_key"] = settings.PUBMED_API_KEY

    try:
        async with httpx.AsyncClient(timeout=settings.PUBMED_TIMEOUT_SECONDS) as client:
            resp = await client.get(EFETCH_URL, params=params)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        articles = []
        for art_elem in root.findall("PubmedArticle"):
            parsed = _parse_article(art_elem)
            if parsed and parsed.get("title") and parsed.get("first_author"):
                articles.append(parsed)

        logger.info("PubMed EFetch: %d/%d articles parsed", len(articles), len(pmids))
        return articles

    except Exception as e:
        logger.warning("PubMed EFetch failed: %s", e)
        return []


async def _get_cached(db: AsyncSession, cid: str) -> tuple[list[PubmedCache], bool]:
    """Retorna artigos cacheados e se o cache é fresco (dentro do TTL)."""
    cid_upper = cid.strip().upper()
    stmt = select(PubmedCache).where(
        PubmedCache.cid == cid_upper
    ).order_by(PubmedCache.created_at.desc())
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        return [], False

    ttl = timedelta(days=settings.PUBMED_CACHE_TTL_DAYS)
    newest = rows[0].created_at
    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    is_fresh = (datetime.now(timezone.utc) - newest) < ttl

    return list(rows), is_fresh


async def _save_to_cache(db: AsyncSession, cid: str, search_term: str, articles: list[dict]) -> list[PubmedCache]:
    """Salva artigos no cache, ignorando duplicatas por PMID."""
    saved = []
    cid_upper = cid.strip().upper()
    for art in articles:
        existing = await db.execute(
            select(PubmedCache).where(PubmedCache.pmid == art["pmid"])
        )
        if existing.scalar_one_or_none():
            continue

        row = PubmedCache(
            pmid=art["pmid"],
            cid=cid_upper,
            search_term=search_term,
            title=art["title"],
            authors=art["authors"],
            first_author=art["first_author"],
            year=art["year"],
            journal=art.get("journal", ""),
            abstract=art.get("abstract", ""),
            article_type=art.get("article_type", "article"),
            doi=art.get("doi", ""),
        )
        db.add(row)
        saved.append(row)

    if saved:
        await db.commit()
        logger.info("PubMed cache: saved %d new articles for CID %s", len(saved), cid_upper)

    return saved


def _cache_to_evidence_dicts(rows: list[PubmedCache]) -> list[dict]:
    """Converte registros PubmedCache em dicts para o pipeline."""
    return [
        {
            "pmid": r.pmid,
            "snippet": (r.abstract or r.title)[:500],
            "autor": r.first_author,
            "authors_full": r.authors,
            "referencia_completa": f"{r.authors}. {r.title}. {r.journal}. {r.year}.",
            "ano": r.year,
            "tipo": r.article_type,
            "journal": r.journal,
            "doi": r.doi,
            "source": "pubmed",
        }
        for r in rows
    ]


async def get_evidences_for_cid(
    db: AsyncSession,
    cid: str,
    product_name: str = "",
    diagnostico: str = "",
) -> list[dict]:
    """
    Busca evidências PubMed para um CID, com cache progressivo.
    Retorna lista de dicts prontos para o Researcher/Writer.
    """
    if not settings.PUBMED_ENABLED:
        logger.info("PubMed disabled (kill switch)")
        return []

    if not cid:
        return []

    cached_rows, is_fresh = await _get_cached(db, cid)

    if cached_rows and is_fresh:
        logger.info("PubMed cache HIT for CID %s (%d articles)", cid, len(cached_rows))
        return _cache_to_evidence_dicts(cached_rows)

    search_term = _cid_to_search_term(cid, product_name, diagnostico)
    pmids = await search_pubmed(search_term, max_results=settings.PUBMED_MAX_RESULTS)

    if not pmids:
        if cached_rows:
            logger.info("PubMed search empty, using stale cache for CID %s", cid)
            return _cache_to_evidence_dicts(cached_rows)
        return []

    articles = await fetch_articles(pmids)
    if not articles:
        if cached_rows:
            return _cache_to_evidence_dicts(cached_rows)
        return []

    await _save_to_cache(db, cid, search_term, articles)

    refreshed_rows, _ = await _get_cached(db, cid)
    return _cache_to_evidence_dicts(refreshed_rows)


async def get_evidences_preview(
    db: AsyncSession,
    cid: str,
    product_name: str = "",
) -> dict:
    """Retorna contagem e preview de evidências para o frontend."""
    from app.db.models import ClinicalEvidence

    cid_upper = cid.strip().upper()

    internal_count = 0
    try:
        stmt = select(func.count()).select_from(ClinicalEvidence).where(
            ClinicalEvidence.cid == cid_upper
        )
        result = await db.execute(stmt)
        internal_count = result.scalar() or 0
    except Exception:
        pass

    pubmed_evidences = await get_evidences_for_cid(db, cid, product_name)
    pubmed_count = len(pubmed_evidences)

    preview = []
    for ev in pubmed_evidences[:5]:
        preview.append({
            "autor": f"{ev['autor']} et al.",
            "ano": ev["ano"],
            "tipo": ev["tipo"],
            "titulo_curto": ev["snippet"][:120] + "..." if len(ev["snippet"]) > 120 else ev["snippet"],
            "pmid": ev["pmid"],
        })

    return {
        "cid": cid_upper,
        "internal_count": internal_count,
        "pubmed_count": pubmed_count,
        "total_count": internal_count + pubmed_count,
        "preview": preview,
    }
