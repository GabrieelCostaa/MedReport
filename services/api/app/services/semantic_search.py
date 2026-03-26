"""
Busca semântica para evidências médicas com txtai + PubMedBERT.

Complementa a busca por keyword do pubmed_service.py:
  1. Keyword search (PubMed cascade) → artigos candidatos
  2. Semantic reranking (este módulo) → reordena por relevância semântica
  3. Cross-encoder reranking (opcional) → reordena com mais precisão

Também permite busca semântica direta sobre evidências já cacheadas no banco.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Lazy initialization — models are heavy, only load when needed
_embeddings = None
_cross_encoder = None
_TXTAI_AVAILABLE: Optional[bool] = None


def _get_embeddings():
    """Lazy-load txtai Embeddings with PubMedBERT."""
    global _embeddings, _TXTAI_AVAILABLE
    if _TXTAI_AVAILABLE is False:
        return None
    if _embeddings is not None:
        return _embeddings
    try:
        from txtai import Embeddings
        _embeddings = Embeddings({
            "path": "NeuML/pubmedbert-base-embeddings",
            "content": True,  # store text alongside vectors
        })
        _TXTAI_AVAILABLE = True
        logger.info("txtai Embeddings loaded (PubMedBERT)")
        return _embeddings
    except Exception as e:
        _TXTAI_AVAILABLE = False
        logger.warning("txtai unavailable, falling back to keyword search: %s", e)
        return None


def _get_cross_encoder():
    """Lazy-load cross-encoder for reranking."""
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder
    try:
        from txtai import CrossEncoder
        _cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        logger.info("Cross-encoder loaded for reranking")
        return _cross_encoder
    except Exception as e:
        logger.warning("Cross-encoder unavailable: %s", e)
        return None


def semantic_rerank(
    query: str,
    evidences: list[dict],
    top_k: int = 10,
    text_field: str = "snippet",
) -> list[dict]:
    """
    Rerank evidences by semantic similarity to the query using PubMedBERT embeddings.

    Args:
        query: Clinical query (e.g., "viscossuplementação para gonartrose M17.0")
        evidences: List of evidence dicts (must have text_field key)
        top_k: Max results to return
        text_field: Which field to use for similarity ("snippet" or "titulo")

    Returns:
        Reranked list of evidences (most relevant first), with added "semantic_score" field
    """
    if not evidences:
        return evidences

    embeddings = _get_embeddings()
    if embeddings is None:
        return evidences[:top_k]  # fallback: return as-is

    try:
        # Build index from evidence texts
        texts = []
        for i, ev in enumerate(evidences):
            text = ev.get(text_field, "") or ev.get("snippet", "") or ""
            titulo = ev.get("titulo", "") or ev.get("title", "") or ""
            combined = f"{titulo}. {text}" if titulo else text
            texts.append((i, combined, None))

        embeddings.index(texts)

        # Search
        results = embeddings.search(query, limit=min(top_k, len(evidences)))

        # Map back to original evidences with scores
        reranked = []
        seen = set()
        for result in results:
            idx = result["id"]
            if idx in seen:
                continue
            seen.add(idx)
            ev = evidences[idx].copy()
            ev["semantic_score"] = round(result["score"], 4)
            reranked.append(ev)

        # Add remaining evidences not in top results (preserve all)
        for i, ev in enumerate(evidences):
            if i not in seen and len(reranked) < len(evidences):
                ev_copy = ev.copy()
                ev_copy["semantic_score"] = 0.0
                reranked.append(ev_copy)

        return reranked[:top_k]

    except Exception as e:
        logger.warning("Semantic rerank failed, returning original order: %s", e)
        return evidences[:top_k]


def cross_encoder_rerank(
    query: str,
    evidences: list[dict],
    top_k: int = 10,
    text_field: str = "snippet",
) -> list[dict]:
    """
    Rerank with cross-encoder (more accurate than bi-encoder, but slower).
    Use after semantic_rerank for a two-stage pipeline:
      1. semantic_rerank (fast, filters to top_k=20)
      2. cross_encoder_rerank (precise, reorders top_k=10)
    """
    if not evidences:
        return evidences

    ce = _get_cross_encoder()
    if ce is None:
        return evidences[:top_k]

    try:
        texts = []
        for ev in evidences:
            text = ev.get(text_field, "") or ev.get("snippet", "") or ""
            titulo = ev.get("titulo", "") or ev.get("title", "") or ""
            combined = f"{titulo}. {text}" if titulo else text
            texts.append(combined)

        # Cross-encoder scores each (query, text) pair
        scores = ce.rank(query, texts)

        # Sort by score descending
        scored = list(zip(scores, evidences))
        scored.sort(key=lambda x: x[0]["score"], reverse=True)

        reranked = []
        for score_info, ev in scored[:top_k]:
            ev_copy = ev.copy()
            ev_copy["rerank_score"] = round(score_info["score"], 4)
            reranked.append(ev_copy)

        return reranked

    except Exception as e:
        logger.warning("Cross-encoder rerank failed: %s", e)
        return evidences[:top_k]


def build_clinical_query(cid: str, product_name: str, diagnostico: str) -> str:
    """
    Build a natural-language clinical query for semantic search.
    More effective than MeSH terms for embedding-based search.
    """
    parts = []
    if diagnostico:
        parts.append(diagnostico)
    if cid:
        parts.append(f"CID {cid}")
    if product_name:
        parts.append(f"treatment with {product_name}")
    return " ".join(parts) if parts else "medical treatment outcome"
