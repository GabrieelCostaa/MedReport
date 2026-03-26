"""
Build the medical knowledge graph from existing MedReport data.

Seeds 3 tiers:
  Tier 1: Products → TUSS → ANVISA
  Tier 2: ClinicalEvidence → PubMed → DUT
  Tier 3: ICD-10 → MeSH (→ UMLS/SNOMED via API, if UMLS_API_KEY set)

Usage:
  cd services/api
  PYTHONPATH=. python3 scripts/build_knowledge_graph.py
"""
import asyncio
import logging
import uuid

from sqlalchemy import select, text as sql_text
from app.db.session import AsyncSessionLocal, engine
from app.db.models import (
    Product, ProductTussMapping, ClinicalEvidence, PubmedCache, DutRule,
    MedicalConcept, ConceptRelation, Base,
)
from app.services.pubmed_service import CID_DESCRIPTIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def ensure_concept(db, code, code_system, name, semantic_type=None, name_en=None):
    """Get or create a MedicalConcept. Returns UUID string."""
    result = await db.execute(
        select(MedicalConcept).where(
            MedicalConcept.code == code,
            MedicalConcept.code_system == code_system,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        return str(existing.id)

    concept = MedicalConcept(
        code=code, code_system=code_system, name=name,
        name_en=name_en, semantic_type=semantic_type,
    )
    db.add(concept)
    await db.flush()
    return str(concept.id)


async def ensure_relation(db, source_id, target_id, relation_type, source_system="medreport", confidence=1.0):
    """Create edge if not exists."""
    exists = await db.execute(sql_text(
        "SELECT 1 FROM concept_relations WHERE source_id = :s AND target_id = :t AND relation_type = :r LIMIT 1"
    ), {"s": source_id, "t": target_id, "r": relation_type})
    if exists.scalar():
        return
    rel = ConceptRelation(
        source_id=source_id, target_id=target_id,
        relation_type=relation_type, source_system=source_system, confidence=confidence,
    )
    db.add(rel)


async def main():
    # Create tables if needed
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        stats = {"concepts": 0, "relations": 0}

        # ── Tier 3: ICD-10 → MeSH ────────────────────────────────────
        logger.info("Tier 3: Seeding ICD-10 → MeSH...")
        for cid_code, (desc_en, mesh_query) in CID_DESCRIPTIONS.items():
            cid_id = await ensure_concept(db, cid_code, "ICD10", desc_en,
                                          semantic_type="Disease", name_en=desc_en)
            mesh_name = mesh_query.replace('"', '').replace('[mh]', '').strip()
            mesh_id = await ensure_concept(db, mesh_name, "MESH", mesh_name,
                                           semantic_type="Disease")
            await ensure_relation(db, cid_id, mesh_id, "maps_to", "pubmed_service")
            stats["concepts"] += 2
            stats["relations"] += 1

        # ── Tier 1: Products → TUSS → ANVISA ─────────────────────────
        logger.info("Tier 1: Linking Products...")
        products = (await db.execute(select(Product))).scalars().all()
        for p in products:
            prod_id = await ensure_concept(db, str(p.id), "PRODUCT", p.nome,
                                           semantic_type="Device")
            stats["concepts"] += 1

            # TUSS mappings
            mappings = (await db.execute(
                select(ProductTussMapping).where(ProductTussMapping.product_id == p.id)
            )).scalars().all()
            for m in mappings:
                tuss_id = await ensure_concept(db, m.tuss_code, "TUSS", m.procedure_name,
                                               semantic_type="Procedure")
                await ensure_relation(db, prod_id, tuss_id, "has_procedure", "product_tuss")
                await ensure_relation(db, tuss_id, prod_id, "uses_device", "product_tuss")
                stats["concepts"] += 1
                stats["relations"] += 2

            # ANVISA
            if p.registro_anvisa:
                anvisa_id = await ensure_concept(db, p.registro_anvisa, "ANVISA",
                                                  f"Registro {p.registro_anvisa}",
                                                  semantic_type="Regulatory")
                await ensure_relation(db, prod_id, anvisa_id, "has_registration", "anvisa")
                stats["concepts"] += 1
                stats["relations"] += 1

            # Link product to CIDs via indicações
            indicacoes = (getattr(p, "indicacoes", "") or "").lower()
            for cid_code in CID_DESCRIPTIONS:
                desc_lower = CID_DESCRIPTIONS[cid_code][0].lower()
                # Simple keyword match between product indications and CID description
                if any(kw in indicacoes for kw in desc_lower.split()[:3] if len(kw) > 4):
                    cid_id = await ensure_concept(db, cid_code, "ICD10",
                                                   CID_DESCRIPTIONS[cid_code][0],
                                                   semantic_type="Disease")
                    await ensure_relation(db, prod_id, cid_id, "indicated_for", "product_indication")
                    stats["relations"] += 1

        # ── Tier 2: Clinical Evidences ────────────────────────────────
        logger.info("Tier 2: Linking Clinical Evidences...")
        evidences = (await db.execute(select(ClinicalEvidence))).scalars().all()
        for ev in evidences:
            ev_id = await ensure_concept(db, str(ev.id), "EVIDENCE",
                                          f"{ev.autor} ({ev.ano}): {ev.snippet[:100]}",
                                          semantic_type="Evidence")
            stats["concepts"] += 1

            # Link to CID
            cid_id = await ensure_concept(db, ev.cid, "ICD10",
                                           CID_DESCRIPTIONS.get(ev.cid, (ev.cid, ""))[0] or ev.cid,
                                           semantic_type="Disease")
            await ensure_relation(db, cid_id, ev_id, "has_evidence", "clinical_evidence")
            stats["relations"] += 1

            # Link to Product
            prod_result = await db.execute(
                select(MedicalConcept).where(
                    MedicalConcept.code == str(ev.product_id),
                    MedicalConcept.code_system == "PRODUCT",
                )
            )
            prod_node = prod_result.scalar_one_or_none()
            if prod_node:
                await ensure_relation(db, str(prod_node.id), ev_id, "supported_by", "clinical_evidence")
                stats["relations"] += 1

        # ── Tier 2: PubMed Cache ──────────────────────────────────────
        logger.info("Tier 2: Linking PubMed articles...")
        articles = (await db.execute(select(PubmedCache))).scalars().all()
        for a in articles:
            art_id = await ensure_concept(db, a.pmid, "PUBMED",
                                           f"{a.first_author} ({a.year}): {a.title[:100]}",
                                           semantic_type="Literature")
            cid_id = await ensure_concept(db, a.cid, "ICD10",
                                           CID_DESCRIPTIONS.get(a.cid, (a.cid, ""))[0] or a.cid,
                                           semantic_type="Disease")
            await ensure_relation(db, cid_id, art_id, "referenced_in", "pubmed_cache")
            stats["concepts"] += 1
            stats["relations"] += 1

        # ── Tier 2: DUT Rules ─────────────────────────────────────────
        logger.info("Tier 2: Linking DUT rules...")
        try:
            duts = (await db.execute(select(DutRule))).scalars().all()
            for d in duts:
                dut_id = await ensure_concept(db, d.numero_dut, "DUT",
                                               d.titulo[:200], semantic_type="Regulatory")
                if d.procedimento_codigo:
                    tuss_result = await db.execute(
                        select(MedicalConcept).where(
                            MedicalConcept.code == d.procedimento_codigo,
                            MedicalConcept.code_system == "TUSS",
                        )
                    )
                    tuss_node = tuss_result.scalar_one_or_none()
                    if tuss_node:
                        await ensure_relation(db, str(tuss_node.id), dut_id, "requires_dut", "ans")
                        stats["relations"] += 1
                stats["concepts"] += 1
        except Exception as e:
            logger.warning("DUT linking skipped: %s", e)

        await db.commit()

        # Count final
        total_concepts = (await db.execute(sql_text("SELECT count(*) FROM medical_concepts"))).scalar()
        total_relations = (await db.execute(sql_text("SELECT count(*) FROM concept_relations"))).scalar()

        logger.info("=" * 50)
        logger.info("Knowledge Graph built successfully!")
        logger.info("  Concepts: %d", total_concepts)
        logger.info("  Relations: %d", total_relations)
        logger.info("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
