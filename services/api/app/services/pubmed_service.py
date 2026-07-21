"""
Serviço de integração com PubMed E-utilities (NCBI) + Europe PMC fallback.
Busca artigos científicos e mantém cache progressivo no Postgres.

Estratégia de busca em cascata:
  1. Cache fresco → retorna imediato (0s)
  2. Busca ESPECÍFICA: MeSH + produto + filtro RCT/meta-analysis
  3. Busca AMPLA: MeSH + categoria genérica do produto
  4. Busca GENÉRICA: só MeSH + "treatment outcome"
  5. ELink: artigos relacionados a PMIDs já conhecidos
  6. Europe PMC: fallback sem rate limit
  7. Salva TUDO no cache → próxima consulta = instantânea
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

# --- NCBI E-utilities URLs ---
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"

# --- Europe PMC URL ---
EUROPEPMC_SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

# HTTP timeout para buscas em cascata (cada etapa)
_TIMEOUT = max(settings.PUBMED_TIMEOUT_SECONDS, 10)

# ---------------------------------------------------------------------------
# CID → MeSH/Descrição expandido (~60 condições)
# ---------------------------------------------------------------------------
CID_DESCRIPTIONS = {
    # Osteoartrite
    "M17.0": ("knee osteoarthritis", '"Osteoarthritis, Knee"[mh]'),
    "M17.1": ("knee osteoarthritis", '"Osteoarthritis, Knee"[mh]'),
    "M17.9": ("knee osteoarthritis", '"Osteoarthritis, Knee"[mh]'),
    "M16.0": ("hip osteoarthritis", '"Osteoarthritis, Hip"[mh]'),
    "M16.1": ("hip osteoarthritis", '"Osteoarthritis, Hip"[mh]'),
    "M16.9": ("hip osteoarthritis", '"Osteoarthritis, Hip"[mh]'),
    # Coluna
    "M54.5": ("low back pain", '"Low Back Pain"[mh]'),
    "M54.1": ("radiculopathy", '"Radiculopathy"[mh]'),
    "M51.1": ("lumbar disc herniation", '"Intervertebral Disc Displacement"[mh]'),
    "M47.8": ("spondylosis", '"Spondylosis"[mh]'),
    "M48.0": ("spinal stenosis", '"Spinal Stenosis"[mh]'),
    # Ombro / membro superior
    "M75.1": ("rotator cuff syndrome", '"Rotator Cuff Injuries"[mh]'),
    "M75.0": ("frozen shoulder adhesive capsulitis", '"Bursitis"[mh]'),
    "M65.3": ("trigger finger", '"Trigger Finger Disorder"[mh]'),
    "M72.0": ("dupuytren contracture", '"Dupuytren Contracture"[mh]'),
    # Joelho / ligamento
    "S83.5": ("anterior cruciate ligament injury", '"Anterior Cruciate Ligament Injuries"[mh]'),
    "S83.0": ("meniscus tear knee", '"Tibial Meniscus Injuries"[mh]'),
    "M23.5": ("chronic knee instability", '"Joint Instability"[mh] AND knee'),
    # Osso / fraturas
    "M84.1": ("nonunion fracture pseudarthrosis", '"Fractures, Ununited"[mh]'),
    "M86.6": ("chronic osteomyelitis", '"Osteomyelitis"[mh]'),
    "M80.0": ("osteoporosis pathological fracture", '"Osteoporotic Fractures"[mh]'),
    "M87.0": ("avascular necrosis bone", '"Osteonecrosis"[mh]'),
    # Hérnia
    "K43.1": ("incisional hernia recurrent", '"Incisional Hernia"[mh]'),
    "K43.9": ("incisional hernia", '"Incisional Hernia"[mh]'),
    "K40.9": ("inguinal hernia", '"Hernia, Inguinal"[mh]'),
    "K40.3": ("inguinal hernia recurrent", '"Hernia, Inguinal"[mh] AND recurrence'),
    "K42.9": ("umbilical hernia", '"Hernia, Umbilical"[mh]'),
    # Aderências
    "K56.5": ("intestinal adhesions", '"Tissue Adhesions"[mh] AND abdomen'),
    "K66.0": ("peritoneal adhesions", '"Tissue Adhesions"[mh] AND peritoneal'),
    "N73.6": ("pelvic adhesions", '"Tissue Adhesions"[mh] AND pelvic'),
    # Urologia
    "N48.6": ("peyronie disease", '"Penile Induration"[mh]'),
    "N40.1": ("benign prostatic hyperplasia", '"Prostatic Hyperplasia"[mh]'),
    "N13.3": ("hydronephrosis", '"Hydronephrosis"[mh]'),
    # Otorrinolaringologia
    "J34.3": ("nasal turbinate hypertrophy", '"Nasal Obstruction"[mh] AND turbinate'),
    "J32.9": ("chronic sinusitis", '"Sinusitis"[mh]'),
    "J35.1": ("tonsillar hypertrophy", '"Palatine Tonsil"[mh] AND hypertrophy'),
    "J38.0": ("vocal cord paralysis", '"Vocal Cord Paralysis"[mh]'),
    # Vascular
    "I83.0": ("varicose veins lower extremities", '"Varicose Veins"[mh]'),
    "I87.2": ("chronic venous insufficiency", '"Venous Insufficiency"[mh]'),
    # Pé diabético / úlceras
    "E11.5": ("diabetic foot ulcer", '"Diabetic Foot"[mh]'),
    "L97": ("chronic venous ulcer", '"Leg Ulcer"[mh]'),
    "L97.9": ("chronic ulcer lower limb", '"Leg Ulcer"[mh]'),
    # Mama
    "C50.9": ("breast neoplasm", '"Breast Neoplasms"[mh]'),
    "N60.9": ("breast reconstruction", '"Mammaplasty"[mh]'),
    "N62": ("gynecomastia", '"Gynecomastia"[mh]'),
    # Lipedema
    "E88.2": ("lipedema", '"Lipedema"[mh] OR lipedema[tiab]'),
    # Neurologia
    "G62.9": ("peripheral neuropathy", '"Peripheral Nervous System Diseases"[mh]'),
    "G56.0": ("carpal tunnel syndrome", '"Carpal Tunnel Syndrome"[mh]'),
    # Dor / tecidos moles
    "M79.1": ("myalgia chronic pain", '"Myalgia"[mh]'),
    "L90.5": ("skin atrophy lipoatrophy", '"Lipoatrophy"[mh]'),
    # Oftalmologia
    "H25.9": ("cataract", '"Cataract"[mh]'),
    "H40.1": ("open angle glaucoma", '"Glaucoma, Open-Angle"[mh]'),
}

# ---------------------------------------------------------------------------
# Produto → termos de busca
# ---------------------------------------------------------------------------
PRODUCT_SEARCH_TERMS = {
    # Chave: palavra no nome do produto (lowercase) → (termos específicos, termos genéricos)
    "laser": (
        "laser surgery OR laser therapy OR photobiomodulation",
        "laser[tiab]",
    ),
    "enxerto": (
        "stromal vascular fraction OR bone graft OR tissue graft",
        "graft[tiab] OR transplantation[tiab]",
    ),
    "svf": (
        "stromal vascular fraction OR adipose derived stem cells",
        "cell therapy OR regenerative medicine",
    ),
    "ec2": (
        "stromal vascular fraction OR fat grafting OR lipotransfer",
        "regenerative medicine",
    ),
    "opus": (
        "hyaluronic acid viscosupplementation OR cross-linked hyaluronic acid",
        "viscosupplementation[tiab]",
    ),
    "hialurônico": (
        "hyaluronic acid viscosupplementation",
        "viscosupplementation[tiab]",
    ),
    "hialuronico": (
        "hyaluronic acid viscosupplementation",
        "viscosupplementation[tiab]",
    ),
    "adhesion": (
        "adhesion barrier OR anti-adhesion OR adhesion prevention",
        "adhesion[tiab] AND prevention",
    ),
    "aderência": (
        "adhesion barrier OR anti-adhesion OR adhesion prevention",
        "adhesion[tiab] AND prevention",
    ),
    "parafuso": (
        "bioabsorbable interference screw OR bioabsorbable screw fixation",
        "orthopedic fixation devices[mh]",
    ),
    "bioabsorv": (
        "bioabsorbable interference screw OR bioabsorbable implant",
        "bioabsorbable[tiab]",
    ),
    "tela": (
        "surgical mesh hernia repair OR polypropylene mesh",
        '"Surgical Mesh"[mh]',
    ),
    "polipropileno": (
        "polypropylene mesh hernia repair",
        '"Surgical Mesh"[mh]',
    ),
    "mesh": (
        "surgical mesh hernia repair",
        '"Surgical Mesh"[mh]',
    ),
    "lipedema": (
        "lipedema liposuction treatment",
        "lipedema[tiab]",
    ),
    "biovidro": (
        "bioactive glass bone regeneration OR bioglass scaffold",
        "bioactive glass[tiab]",
    ),
    "biossilex": (
        "bioactive glass bone regeneration OR bioglass scaffold",
        "bioactive glass[tiab]",
    ),
    "vitagraft": (
        "biphasic calcium phosphate bone graft OR hydroxyapatite TCP scaffold",
        "bone substitute[tiab] OR bone graft[tiab]",
    ),
    "bifásico": (
        "biphasic calcium phosphate bone graft",
        "calcium phosphate[tiab] AND bone",
    ),
}

# Filtros de tipo de publicação (do mais forte ao mais fraco)
EVIDENCE_FILTER_STRONG = '("meta-analysis"[pt] OR "systematic review"[pt] OR "randomized controlled trial"[pt])'
EVIDENCE_FILTER_BROAD = '("clinical trial"[pt] OR "meta-analysis"[pt] OR "review"[pt])'
EVIDENCE_FILTER_MINIMAL = '("review"[pt] OR "journal article"[pt])'

# ---------------------------------------------------------------------------
# Dicionário médico PT→EN para fallback de CIDs desconhecidos
# Permite busca PubMed mesmo quando o CID não está no mapeamento manual
# ---------------------------------------------------------------------------
_MEDICAL_PT_EN = {
    # Anatomia
    "joelho": "knee", "quadril": "hip", "ombro": "shoulder", "coluna": "spine",
    "tornozelo": "ankle", "punho": "wrist", "cotovelo": "elbow", "mão": "hand",
    "pé": "foot", "fêmur": "femur", "tíbia": "tibia", "úmero": "humerus",
    "pelve": "pelvis", "sacro": "sacrum", "lombar": "lumbar", "cervical": "cervical",
    "torácica": "thoracic", "nasal": "nasal", "corneto": "turbinate",
    "mama": "breast", "próstata": "prostate", "rim": "kidney", "fígado": "liver",
    "pulmão": "lung", "intestino": "intestine", "abdome": "abdomen", "pênis": "penis",
    "bexiga": "bladder", "útero": "uterus", "ovário": "ovary", "tireóide": "thyroid",
    # Patologias
    "artrose": "osteoarthritis", "gonartrose": "knee osteoarthritis",
    "coxartrose": "hip osteoarthritis", "artrite": "arthritis",
    "hérnia": "hernia", "fratura": "fracture", "ruptura": "rupture",
    "lesão": "injury", "luxação": "dislocation", "instabilidade": "instability",
    "estenose": "stenosis", "compressão": "compression", "infecção": "infection",
    "inflamação": "inflammation", "necrose": "necrosis", "fibrose": "fibrosis",
    "tumor": "tumor", "neoplasia": "neoplasm", "câncer": "cancer",
    "úlcera": "ulcer", "abscesso": "abscess", "osteomielite": "osteomyelitis",
    "pseudoartrose": "nonunion", "aderência": "adhesion", "aderências": "adhesions",
    "hipertrofia": "hypertrophy", "obstrução": "obstruction", "degeneração": "degeneration",
    "displasia": "dysplasia", "neuropatia": "neuropathy", "tendinite": "tendinitis",
    "bursite": "bursitis", "sinovite": "synovitis", "menisco": "meniscus",
    "ligamento": "ligament", "tendão": "tendon", "cartilagem": "cartilage",
    "osteoporose": "osteoporosis", "escoliose": "scoliosis", "cifose": "kyphosis",
    "lordose": "lordosis", "protrusão": "protrusion", "extrusão": "extrusion",
    # Qualificadores
    "crônica": "chronic", "crônico": "chronic", "aguda": "acute", "agudo": "acute",
    "recidivada": "recurrent", "recidivante": "recurrent", "bilateral": "bilateral",
    "unilateral": "unilateral", "primária": "primary", "secundária": "secondary",
    "incisional": "incisional", "inguinal": "inguinal", "umbilical": "umbilical",
    # Procedimentos
    "artroplastia": "arthroplasty", "artroscopia": "arthroscopy",
    "viscossuplementação": "viscosupplementation", "osteossíntese": "osteosynthesis",
    "hernioplastia": "hernioplasty", "laminectomia": "laminectomy",
    "discectomia": "discectomy", "turbinectomia": "turbinectomy",
    "turbinoplastia": "turbinoplasty", "mastectomia": "mastectomy",
    "reconstrução": "reconstruction", "enxerto": "graft", "implante": "implant",
    "prótese": "prosthesis", "tela": "mesh", "parafuso": "screw",
    # Materiais
    "biovidro": "bioactive glass", "polipropileno": "polypropylene",
    "bioabsorvível": "bioabsorbable", "titânio": "titanium",
    "hialurônico": "hyaluronic acid", "colágeno": "collagen",
}


def _translate_diagnosis_to_english(diagnostico: str) -> str:
    """
    Traduz diagnóstico PT→EN usando dicionário médico.
    Não precisa ser perfeito — PubMed é tolerante com termos aproximados.
    """
    if not diagnostico:
        return ""

    words = diagnostico.lower().split()
    translated = []
    i = 0
    while i < len(words):
        # Tenta bigram primeiro (ex: "ácido hialurônico")
        if i + 1 < len(words):
            bigram = f"{words[i]} {words[i+1]}"
            if bigram in _MEDICAL_PT_EN:
                translated.append(_MEDICAL_PT_EN[bigram])
                i += 2
                continue

        word = words[i]
        if word in _MEDICAL_PT_EN:
            translated.append(_MEDICAL_PT_EN[word])
        elif len(word) > 5 and not word.isdigit():
            # Tenta match parcial — exige prefixo de 5+ chars para evitar falsos positivos
            for pt, en in _MEDICAL_PT_EN.items():
                if len(pt) > 5 and (pt.startswith(word[:5]) or word.startswith(pt[:5])):
                    translated.append(en)
                    break
        i += 1

    return " ".join(translated) if translated else ""


# ---------------------------------------------------------------------------
# Construção de queries em cascata
# ---------------------------------------------------------------------------

def _get_product_terms(product_name: str) -> tuple[str, str]:
    """Retorna (termos_específicos, termos_genéricos) para o produto."""
    if not product_name:
        return "", ""
    clean = product_name.lower()
    for keyword, (specific, generic) in PRODUCT_SEARCH_TERMS.items():
        if keyword in clean:
            return specific, generic
    return "", ""


async def _llm_cid_to_mesh(cid: str, diagnostico: str) -> Optional[tuple[str, str]]:
    """Traduz diagnóstico PT + CID → (descrição EN, fragmento de query MeSH) via LLM barato.

    Só usado na CAUDA LONGA (CID fora de CID_DESCRIPTIONS). Custo ~irrisório
    (gpt-4o-mini). Retorna None em qualquer falha → o chamador cai no heurístico.
    """
    if not settings.OPENAI_API_KEY or not diagnostico:
        return None
    try:
        import json as _json
        import openai
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        prompt = (
            "You map a Brazilian ICD-10 (CID-10) diagnosis to PubMed search terms.\n"
            f"CID-10: {cid}\nDiagnóstico (PT): {diagnostico[:200]}\n\n"
            'Return STRICT JSON: {"desc_en": "<short English disease name>", '
            '"mesh": "<a PubMed query fragment, prefer an official MeSH term like '
            '\\"Heart Failure\\"[mh], else free-text[tiab]>"}. No prose.'
        )
        resp = await client.chat.completions.create(
            model=settings.OPENAI_MODEL_TRANSLATOR,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=120,
        )
        data = _json.loads(resp.choices[0].message.content)
        desc_en = (data.get("desc_en") or "").strip()
        mesh = (data.get("mesh") or "").strip()
        if desc_en and mesh:
            logger.info("CID %s traduzido via LLM: '%s' → %s", cid, desc_en, mesh)
            return desc_en, mesh
    except Exception as e:
        logger.debug("LLM CID→MeSH falhou para %s: %s", cid, e)
    return None


async def _resolve_cid_terms(
    db: Optional[AsyncSession], cid: str, diagnostico: str
) -> tuple[Optional[str], Optional[str]]:
    """Resolve (desc_text, mesh_term) para um CID.

    Ordem: dict estático → cache DB (MedicalConcept ICD10) → LLM (persiste) →
    heurístico PT→EN. Só chama o LLM na cauda longa e cacheia o resultado.
    """
    cid_upper = cid.strip().upper()
    entry = CID_DESCRIPTIONS.get(cid_upper)
    if entry:
        return entry[0], entry[1]

    # Cache persistente em MedicalConcept (name = desc_en, name_en = mesh)
    if db is not None:
        try:
            from app.db.models import MedicalConcept
            row = (await db.execute(
                select(MedicalConcept).where(
                    MedicalConcept.code == cid_upper,
                    MedicalConcept.code_system == "ICD10",
                )
            )).scalar_one_or_none()
            if row and row.name_en:
                return (row.name or cid_upper), row.name_en
        except Exception as e:
            logger.debug("Cache CID lookup falhou: %s", e)

    # LLM (cauda longa) → persiste
    llm = await _llm_cid_to_mesh(cid_upper, diagnostico)
    if llm:
        desc_en, mesh = llm
        if db is not None:
            try:
                from app.db.models import MedicalConcept
                db.add(MedicalConcept(
                    code=cid_upper, code_system="ICD10",
                    name=desc_en, name_en=mesh,
                ))
                await db.commit()
            except Exception:
                try:
                    await db.rollback()
                except Exception:
                    pass
        return desc_en, mesh

    # Heurístico final (comportamento legado)
    translated = _translate_diagnosis_to_english(diagnostico)
    if translated:
        return translated, f'"{translated}"[tiab]'
    fallback = diagnostico[:80] if diagnostico else cid_upper
    return fallback, f'"{fallback}"[tiab]'


def _build_cascade_queries(
    cid: str, product_name: str = "", diagnostico: str = "",
    resolved: Optional[tuple] = None,
) -> list[str]:
    """
    Constrói lista de queries do mais específico ao mais amplo.
    A busca para na primeira query que retornar resultados.
    `resolved` = (desc_text, mesh_term) já resolvido (dict/cache/LLM); se None,
    resolve sincronamente pelo dict + heurístico (sem LLM).
    """
    cid_upper = cid.strip().upper()

    if resolved is not None:
        desc_text, mesh_term = resolved
    else:
        cid_entry = CID_DESCRIPTIONS.get(cid_upper)
        if cid_entry:
            desc_text, mesh_term = cid_entry
        else:
            # CID desconhecido: traduz diagnóstico PT→EN para buscar no PubMed
            translated = _translate_diagnosis_to_english(diagnostico)
            if translated:
                desc_text = translated
                mesh_term = f'"{translated}"[tiab]'
                logger.info("CID %s not in dict, translated diagnosis: '%s' → '%s'", cid_upper, diagnostico[:60], translated)
            else:
                desc_text = diagnostico[:80] if diagnostico else cid_upper
                mesh_term = f'"{desc_text}"[tiab]'
                logger.warning("CID %s not in dict and no translation available for: %s", cid_upper, diagnostico[:60])

    specific_product, generic_product = _get_product_terms(product_name)

    queries = []

    # Nível 1: MeSH + produto específico + evidência forte
    if mesh_term and specific_product:
        queries.append(
            f"({mesh_term}) AND ({specific_product}) AND {EVIDENCE_FILTER_STRONG}"
        )

    # Nível 2: MeSH + produto específico + evidência ampla
    if mesh_term and specific_product:
        queries.append(
            f"({mesh_term}) AND ({specific_product}) AND {EVIDENCE_FILTER_BROAD}"
        )

    # Nível 3: MeSH + produto genérico + evidência ampla
    if mesh_term and generic_product:
        queries.append(
            f"({mesh_term}) AND ({generic_product}) AND {EVIDENCE_FILTER_BROAD}"
        )

    # Nível 4: Só MeSH + treatment outcome
    if mesh_term:
        queries.append(
            f'({mesh_term}) AND ("treatment outcome"[mh] OR efficacy[tiab] OR safety[tiab]) AND {EVIDENCE_FILTER_BROAD}'
        )

    # Nível 5: Texto livre (último recurso PubMed)
    if desc_text:
        queries.append(
            f'("{desc_text}"[tiab]) AND {EVIDENCE_FILTER_MINIMAL}'
        )

    return queries


# ---------------------------------------------------------------------------
# PubMed E-utilities (baixo nível)
# ---------------------------------------------------------------------------

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
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(ESEARCH_URL, params=params)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        pmids = [id_elem.text for id_elem in root.findall(".//IdList/Id") if id_elem.text]
        logger.info("PubMed ESearch: query=%s, found=%d PMIDs", query[:100], len(pmids))
        return pmids

    except Exception as e:
        logger.warning("PubMed ESearch failed: %s", e)
        return []


async def search_related(pmids: list[str], max_results: int = 5) -> list[str]:
    """Usa ELink para encontrar artigos relacionados aos PMIDs dados."""
    if not pmids:
        return []

    params = {
        "dbfrom": "pubmed",
        "db": "pubmed",
        "id": ",".join(pmids[:3]),  # Limita a 3 seeds para performance
        "cmd": "neighbor_score",
        "retmode": "xml",
    }
    if settings.PUBMED_API_KEY:
        params["api_key"] = settings.PUBMED_API_KEY

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(ELINK_URL, params=params)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        related_pmids = []
        seen = set(pmids)

        for link in root.findall(".//LinkSetDb/Link"):
            id_elem = link.find("Id")
            if id_elem is not None and id_elem.text and id_elem.text not in seen:
                related_pmids.append(id_elem.text)
                seen.add(id_elem.text)
                if len(related_pmids) >= max_results:
                    break

        logger.info("PubMed ELink: found %d related articles", len(related_pmids))
        return related_pmids

    except Exception as e:
        logger.warning("PubMed ELink failed: %s", e)
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
        elif any("systematic" in t and "review" in t for t in pub_types):
            article_type = "systematic-review"
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
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
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


# ---------------------------------------------------------------------------
# Europe PMC (fallback — sem rate limit, sem API key)
# ---------------------------------------------------------------------------

async def _search_europe_pmc(query: str, max_results: int = 10) -> list[dict]:
    """Busca no Europe PMC como fallback quando PubMed retorna 0."""
    params = {
        "query": query,
        "resultType": "core",
        "pageSize": max_results,
        "format": "json",
        "sort": "RELEVANCE",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(EUROPEPMC_SEARCH_URL, params=params)
            resp.raise_for_status()

        data = resp.json()
        results = data.get("resultList", {}).get("result", [])

        articles = []
        for r in results:
            pmid = r.get("pmid", "")
            if not pmid:
                # Europe PMC pode retornar artigos sem PMID; usar ID interno
                pmid = f"EPMC-{r.get('id', '')}"

            first_author = ""
            authors_str = r.get("authorString", "")
            if authors_str:
                first_author = authors_str.split(",")[0].split(" ")[-1].strip()

            # Classificar tipo
            pub_type = (r.get("pubType") or "").lower()
            article_type = "article"
            if "meta-analysis" in pub_type:
                article_type = "meta-analysis"
            elif "systematic" in pub_type and "review" in pub_type:
                article_type = "systematic-review"
            elif "randomized" in pub_type or "clinical trial" in pub_type:
                article_type = "rct"
            elif "review" in pub_type:
                article_type = "review"

            articles.append({
                "pmid": str(pmid),
                "title": r.get("title", ""),
                "authors": authors_str,
                "first_author": first_author,
                "year": str(r.get("pubYear", "")),
                "journal": r.get("journalTitle", ""),
                "abstract": r.get("abstractText", "")[:2000],
                "article_type": article_type,
                "doi": r.get("doi", ""),
            })

        logger.info("Europe PMC: query=%s, found=%d articles", query[:80], len(articles))
        return [a for a in articles if a["title"] and a["first_author"]]

    except Exception as e:
        logger.warning("Europe PMC search failed: %s", e)
        return []


def _build_europe_pmc_query(
    cid: str, product_name: str = "", diagnostico: str = "",
    resolved: Optional[tuple] = None,
) -> str:
    """Constrói query para Europe PMC (sintaxe diferente do PubMed)."""
    cid_upper = cid.strip().upper()

    if resolved is not None and resolved[0]:
        desc_text = resolved[0]
    else:
        cid_entry = CID_DESCRIPTIONS.get(cid_upper)
        if cid_entry:
            desc_text = cid_entry[0]
        else:
            desc_text = diagnostico[:80] if diagnostico else ""

    specific_product, _ = _get_product_terms(product_name)

    parts = []
    if desc_text:
        parts.append(f'"{desc_text}"')
    if specific_product:
        # Simplificar para Europe PMC (não usa [mh])
        clean_terms = specific_product.replace("[mh]", "").replace("[tiab]", "")
        parts.append(f"({clean_terms})")

    query = " AND ".join(parts) if parts else cid_upper
    # Filtrar por tipo e artigos recentes
    return f"({query}) AND (SRC:MED) AND (PUB_TYPE:review OR PUB_TYPE:research-article)"


# ---------------------------------------------------------------------------
# Cache (PostgreSQL)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Busca principal com cascata
# ---------------------------------------------------------------------------

async def _cascade_search(
    cid: str,
    product_name: str = "",
    diagnostico: str = "",
    max_results: int = 10,
    resolved: Optional[tuple] = None,
) -> tuple[list[dict], str]:
    """
    Busca em cascata: tenta queries do mais específico ao mais amplo.
    Retorna (artigos, query_usada).
    """
    queries = _build_cascade_queries(cid, product_name, diagnostico, resolved=resolved)
    all_pmids = []
    used_query = ""

    import asyncio

    for i, query in enumerate(queries):
        level_timeout = 5.0  # 5s per cascade level
        try:
            pmids = await asyncio.wait_for(
                search_pubmed(query, max_results=max_results),
                timeout=level_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Cascade level %d timed out (%.1fs): %s", i + 1, level_timeout, query[:80])
            continue

        if pmids:
            all_pmids = pmids
            used_query = query
            logger.info("Cascade search HIT at level %d: %s (%d results)", i + 1, query[:80], len(pmids))
            break
        logger.info("Cascade search MISS level %d: %s", i + 1, query[:80])

    if not all_pmids:
        return [], ""

    articles = await fetch_articles(all_pmids)

    # Bonus: buscar artigos relacionados via ELink para enriquecer
    if articles and len(articles) < max_results:
        seed_pmids = [a["pmid"] for a in articles[:3]]
        related_pmids = await search_related(seed_pmids, max_results=max_results - len(articles))
        if related_pmids:
            related_articles = await fetch_articles(related_pmids)
            seen = {a["pmid"] for a in articles}
            for ra in related_articles:
                if ra["pmid"] not in seen:
                    articles.append(ra)
                    seen.add(ra["pmid"])

    return articles, used_query


async def _europe_pmc_fallback(
    cid: str,
    product_name: str = "",
    diagnostico: str = "",
    max_results: int = 10,
    resolved: Optional[tuple] = None,
) -> tuple[list[dict], str]:
    """Fallback para Europe PMC quando PubMed não retorna resultados."""
    query = _build_europe_pmc_query(cid, product_name, diagnostico, resolved=resolved)
    articles = await _search_europe_pmc(query, max_results=max_results)
    return articles, f"[EuropePMC] {query}"


def _rerank_evidences(cid: str, product_name: str, diagnostico: str, evidence_dicts: list[dict]) -> list[dict]:
    """Reordena por relevância clínica. Usa PubMedBERT se disponível (txtai),
    senão rerank léxico com rapidfuzz (sempre disponível, cabe no Render).
    Fail-soft: em qualquer erro retorna a lista original."""
    if not evidence_dicts:
        return evidence_dicts
    try:
        from app.services.semantic_search import build_clinical_query, semantic_rerank, lexical_rerank
        clinical_query = build_clinical_query(cid, product_name, diagnostico)
        top_k = settings.PUBMED_MAX_RESULTS
        try:
            from app.services.semantic_search import _get_embeddings
            has_txtai = _get_embeddings() is not None
        except Exception:
            has_txtai = False
        if has_txtai:
            return semantic_rerank(clinical_query, evidence_dicts, top_k=top_k, text_field="snippet")
        return lexical_rerank(clinical_query, evidence_dicts, top_k=top_k, text_field="snippet")
    except Exception as e:
        logger.debug("Rerank pulado: %s", e)
        return evidence_dicts


# ---------------------------------------------------------------------------
# API pública do serviço
# ---------------------------------------------------------------------------

async def get_evidences_for_cid(
    db: AsyncSession,
    cid: str,
    product_name: str = "",
    diagnostico: str = "",
) -> list[dict]:
    """
    Busca evidências PubMed para um CID, com cache progressivo e busca em cascata.
    Retorna lista de dicts prontos para o Researcher/Writer.

    Fluxo:
    1. Cache fresco → retorno imediato
    2. Cascata PubMed (5 níveis de especificidade)
    3. ELink para artigos relacionados
    4. Europe PMC como fallback
    5. Cache stale como último recurso
    """
    if not settings.PUBMED_ENABLED:
        logger.info("PubMed disabled (kill switch)")
        return []

    if not cid:
        return []

    # 1. Verificar cache (agora com rerank também no hit — rapidfuzz é barato)
    cached_rows, is_fresh = await _get_cached(db, cid)
    if cached_rows and is_fresh:
        logger.info("PubMed cache HIT for CID %s (%d articles)", cid, len(cached_rows))
        return _rerank_evidences(cid, product_name, diagnostico, _cache_to_evidence_dicts(cached_rows))

    # 1.5 Resolve termos de busca (dict → cache DB → LLM barato na cauda longa)
    resolved = await _resolve_cid_terms(db, cid, diagnostico)

    # 2. Busca em cascata PubMed + ELink
    articles, used_query = await _cascade_search(
        cid, product_name, diagnostico, max_results=settings.PUBMED_MAX_RESULTS, resolved=resolved,
    )

    # 3. Europe PMC fallback se PubMed não encontrou nada
    if not articles:
        logger.info("PubMed cascade empty for CID %s, trying Europe PMC...", cid)
        articles, used_query = await _europe_pmc_fallback(
            cid, product_name, diagnostico, max_results=settings.PUBMED_MAX_RESULTS, resolved=resolved,
        )

    # 4. Salvar resultados no cache + rerank
    if articles:
        await _save_to_cache(db, cid, used_query, articles)
        refreshed_rows, _ = await _get_cached(db, cid)
        evidence_dicts = _rerank_evidences(
            cid, product_name, diagnostico, _cache_to_evidence_dicts(refreshed_rows)
        )
        return evidence_dicts

    # 5. Cache stale como último recurso
    if cached_rows:
        logger.info("All searches empty, using stale cache for CID %s", cid)
        return _rerank_evidences(cid, product_name, diagnostico, _cache_to_evidence_dicts(cached_rows))

    logger.warning("No evidence found for CID %s (all sources exhausted)", cid)
    return []


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
