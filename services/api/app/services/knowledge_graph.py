"""
Medical Knowledge Graph RAG service.

3-tiered graph (inspired by MedGraphRAG, ACL 2025):
  Tier 1 (Domain):    Product ↔ TUSS ↔ ANVISA
  Tier 2 (Literature): ClinicalEvidence ↔ PubMed ↔ DUT
  Tier 3 (Ontology):  ICD-10 ↔ UMLS CUI ↔ SNOMED-CT ↔ MeSH

Storage: PostgreSQL adjacency list + recursive CTEs.
Optional: NetworkX in-memory graph for sub-ms queries.

Usage:
  ctx = await query_knowledge_graph(db, "M17.0", product_id)
  prompt_text = format_graph_context_for_llm(ctx)
"""
import logging
import uuid as uuid_mod
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
from sqlalchemy import text as sql_text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MedicalConcept, ConceptRelation

logger = logging.getLogger(__name__)

# ── NetworkX in-memory graph (loaded at startup) ─────────────────────────

_graph: Optional[nx.DiGraph] = None


async def load_graph(db: AsyncSession) -> nx.DiGraph:
    """Load knowledge graph from PostgreSQL into NetworkX. Call once at startup."""
    global _graph
    G = nx.DiGraph()

    concepts = (await db.execute(select(MedicalConcept))).scalars().all()
    for c in concepts:
        G.add_node(
            f"{c.code_system}:{c.code}",
            name=c.name, semantic_type=c.semantic_type or "",
            code=c.code, code_system=c.code_system, db_id=str(c.id),
        )

    relations = (await db.execute(select(ConceptRelation))).scalars().all()
    id_to_key = {str(c.id): f"{c.code_system}:{c.code}" for c in concepts}
    for r in relations:
        src = id_to_key.get(str(r.source_id))
        tgt = id_to_key.get(str(r.target_id))
        if src and tgt:
            G.add_edge(src, tgt, relation=r.relation_type, confidence=r.confidence or 1.0)

    _graph = G
    logger.info("Knowledge graph loaded: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def get_graph() -> Optional[nx.DiGraph]:
    return _graph


# ── Graph Context ─────────────────────────────────────────────────────────

@dataclass
class GraphContext:
    product_info: dict = field(default_factory=dict)
    procedures: list[dict] = field(default_factory=list)
    regulatory: list[dict] = field(default_factory=list)
    clinical_evidences: list[dict] = field(default_factory=list)
    pubmed_articles: list[dict] = field(default_factory=list)
    umls_concepts: list[dict] = field(default_factory=list)
    snomed_concepts: list[dict] = field(default_factory=list)
    related_conditions: list[dict] = field(default_factory=list)
    cid_product_path: list[str] = field(default_factory=list)
    graph_stats: dict = field(default_factory=dict)


# ── Query via NetworkX (fast, in-memory) ──────────────────────────────────

def query_graph_networkx(
    cid: str,
    product_id: str,
    max_depth: int = 3,
) -> GraphContext:
    """Query the in-memory NetworkX graph. Sub-millisecond."""
    G = get_graph()
    if G is None or G.number_of_nodes() == 0:
        return GraphContext()

    cid_node = f"ICD10:{cid}"
    prod_node = f"PRODUCT:{product_id}"

    reachable = set()
    for start in [cid_node, prod_node]:
        if start not in G:
            continue
        for edge in nx.bfs_edges(G, start, depth_limit=max_depth):
            reachable.add(edge[0])
            reachable.add(edge[1])
        for pred in G.predecessors(start):
            reachable.add(pred)

    ctx = GraphContext()
    for node_id in reachable:
        if node_id in (cid_node, prod_node):
            continue
        data = G.nodes.get(node_id, {})
        sem = data.get("semantic_type", "")
        entry = {"node": node_id, "name": data.get("name", ""), "type": sem, "code": data.get("code", "")}

        if sem == "Procedure":
            ctx.procedures.append(entry)
        elif sem == "Evidence":
            ctx.clinical_evidences.append(entry)
        elif sem == "Literature":
            ctx.pubmed_articles.append(entry)
        elif sem == "Regulatory":
            ctx.regulatory.append(entry)
        elif "UMLS" in node_id:
            ctx.umls_concepts.append(entry)
        elif "SNOMED" in node_id:
            ctx.snomed_concepts.append(entry)
        elif sem == "Disease":
            ctx.related_conditions.append(entry)

    # Shortest path for explainability
    try:
        undirected = G.to_undirected()
        if cid_node in undirected and prod_node in undirected:
            ctx.cid_product_path = nx.shortest_path(undirected, cid_node, prod_node)
    except nx.NetworkXNoPath:
        pass

    ctx.graph_stats = {
        "total_nodes": len(reachable),
        "procedures": len(ctx.procedures),
        "evidences": len(ctx.clinical_evidences),
        "articles": len(ctx.pubmed_articles),
    }
    return ctx


# ── Query via PostgreSQL recursive CTE (always fresh) ────────────────────

TRAVERSAL_SQL = """
WITH RECURSIVE graph_walk AS (
    SELECT mc.id, mc.code, mc.code_system, mc.name, mc.semantic_type,
           cr.relation_type, 1 AS depth, ARRAY[mc.id] AS path
    FROM medical_concepts mc
    JOIN concept_relations cr ON cr.source_id = mc.id
    WHERE (mc.code = :code1 AND mc.code_system = :sys1)
       OR (mc.code = :code2 AND mc.code_system = :sys2)
    UNION ALL
    SELECT mc2.id, mc2.code, mc2.code_system, mc2.name, mc2.semantic_type,
           cr2.relation_type, gw.depth + 1, gw.path || mc2.id
    FROM graph_walk gw
    JOIN concept_relations cr2 ON cr2.source_id = gw.id
    JOIN medical_concepts mc2 ON mc2.id = cr2.target_id
    WHERE gw.depth < :max_depth AND mc2.id != ALL(gw.path)
)
SELECT DISTINCT ON (code, code_system) code, code_system, name, semantic_type, relation_type, depth
FROM graph_walk ORDER BY code, code_system, depth
"""


async def query_knowledge_graph(
    db: AsyncSession,
    cid: str,
    product_id: str,
    max_depth: int = 3,
) -> GraphContext:
    """
    Query the knowledge graph. Uses NetworkX if loaded, falls back to PostgreSQL CTE.
    """
    # Try NetworkX first (sub-ms)
    G = get_graph()
    if G is not None and G.number_of_nodes() > 0:
        return query_graph_networkx(cid, product_id, max_depth)

    # Fallback: PostgreSQL recursive CTE
    try:
        result = await db.execute(
            sql_text(TRAVERSAL_SQL),
            {"code1": cid, "sys1": "ICD10", "code2": product_id, "sys2": "PRODUCT", "max_depth": max_depth},
        )
        rows = [dict(r._mapping) for r in result.fetchall()]
    except Exception as e:
        logger.warning("Graph CTE query failed: %s", e)
        return GraphContext()

    ctx = GraphContext()
    for row in rows:
        sem = row.get("semantic_type", "")
        entry = {"code": row["code"], "system": row["code_system"], "name": row["name"], "depth": row["depth"]}
        if sem == "Procedure":
            ctx.procedures.append(entry)
        elif sem == "Evidence":
            ctx.clinical_evidences.append(entry)
        elif sem == "Literature":
            ctx.pubmed_articles.append(entry)
        elif sem == "Regulatory":
            ctx.regulatory.append(entry)
        elif row["code_system"] == "UMLS":
            ctx.umls_concepts.append(entry)
        elif row["code_system"] == "SNOMED":
            ctx.snomed_concepts.append(entry)
        elif sem == "Disease":
            ctx.related_conditions.append(entry)

    ctx.graph_stats = {"total_nodes": len(rows), "procedures": len(ctx.procedures)}
    return ctx


# ── Format for LLM prompt ─────────────────────────────────────────────────

def format_graph_context_for_llm(ctx: GraphContext) -> str:
    """Format GraphContext into structured text for LLM injection."""
    if not any([ctx.procedures, ctx.clinical_evidences, ctx.pubmed_articles, ctx.regulatory, ctx.umls_concepts]):
        return ""

    parts = ["=== CONTEXTO DO GRAFO DE CONHECIMENTO MÉDICO ==="]

    if ctx.procedures:
        parts.append("\nPROCEDIMENTOS RELACIONADOS (TUSS):")
        for p in ctx.procedures[:10]:
            parts.append(f"  - {p.get('code', '')} {p['name']}")

    if ctx.clinical_evidences:
        parts.append(f"\nEVIDÊNCIAS CLÍNICAS CONECTADAS: {len(ctx.clinical_evidences)} encontrada(s)")

    if ctx.pubmed_articles:
        parts.append(f"\nARTIGOS PUBMED CONECTADOS: {len(ctx.pubmed_articles)} artigo(s)")

    if ctx.regulatory:
        parts.append("\nREQUISITOS REGULATÓRIOS:")
        for r in ctx.regulatory[:5]:
            parts.append(f"  - [{r.get('system', r.get('code', ''))}] {r['name'][:150]}")

    if ctx.umls_concepts:
        parts.append("\nCONCEITOS UMLS:")
        for u in ctx.umls_concepts[:5]:
            parts.append(f"  - CUI {u.get('code', '')}: {u['name']}")

    if ctx.snomed_concepts:
        parts.append("\nCONCEITOS SNOMED-CT:")
        for s in ctx.snomed_concepts[:5]:
            parts.append(f"  - {s.get('code', '')}: {s['name']}")

    if ctx.cid_product_path:
        parts.append(f"\nCAMINHO CID→PRODUTO: {' → '.join(ctx.cid_product_path)}")

    return "\n".join(parts)
