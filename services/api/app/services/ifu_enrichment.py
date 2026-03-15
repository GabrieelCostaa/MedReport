"""
Enriquecimento de produtos OPME via Instruções de Uso (IFU) dos fabricantes.

Zero custo — baixa PDFs públicos de instruções de uso, extrai texto com PyMuPDF
e parseia seções padronizadas (IN nº 4/2012 ANVISA):
  1. Descrição
  3. Indicações
  5. Contraindicações
  9. Riscos de Implantação

Fontes:
  - Sites dos fabricantes (ex: ortosintese.com.br/instrucoes-de-uso)
  - Repositório ANVISA (consultas.anvisa.gov.br)
"""
import io
import re
import logging
from typing import Optional

import httpx

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product

logger = logging.getLogger(__name__)

# ── Known manufacturer IFU page patterns ─────────────────────────────────
# Maps normalized fabricante substrings to their IFU listing pages
MANUFACTURER_IFU_PAGES = {
    "ortosintese": "https://www.ortosintese.com.br/instrucoes-de-uso",
    "biodevice": "https://biodevice.com.br/instrucoes-de-uso",
}

# HTTP client config
HTTP_TIMEOUT = 30.0
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

# Section patterns for IFU parsing (IN nº 4/2012 ANVISA standard)
SECTION_PATTERNS = [
    (r"(?:^|\n)\s*\d+[\.\)]\s*DESCRI[CÇ][AÃ]O\b", "descricao"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*INDICA[CÇ][OÕ]ES\b", "indicacoes"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*INFORMA[CÇ][OÕ]ES DE USO\b", "informacoes_uso"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*CONTRAINDICA[CÇ][OÕ]ES\b", "contraindicacoes"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*AVISOS\b", "avisos"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*PRECAU[CÇ][OÕ]ES\b", "precaucoes"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*ADVERT[EÊ]NCIAS\b", "advertencias"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*RISCOS\b", "riscos"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*EMBALAGEM\b", "embalagem"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*CUIDADOS ESPECIAIS\b", "cuidados"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*ESTERILIZA[CÇ][AÃ]O\b", "esterilizacao"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*RASTREABILIDADE\b", "rastreabilidade"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*INSTRU[CÇ][OÕ]ES DE USO\b", "instrucoes_uso"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*MODELO DE ROTULAGEM\b", "rotulagem"),
    (r"(?:^|\n)\s*\d+[\.\)]\s*FORMAS DE APRESENTA[CÇ][AÃ]O\b", "apresentacao"),
]


# ── PDF Discovery ────────────────────────────────────────────────────────

async def _find_pdf_from_manufacturer(registro: str, fabricante: str) -> Optional[str]:
    """Try to find IFU PDF URL from known manufacturer websites."""
    fabricante_lower = (fabricante or "").lower()

    for key, page_url in MANUFACTURER_IFU_PAGES.items():
        if key not in fabricante_lower:
            continue

        logger.info("Buscando IFU em %s para registro %s", page_url, registro)
        try:
            async with httpx.AsyncClient(
                headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True
            ) as client:
                resp = await client.get(page_url)
                resp.raise_for_status()
                html = resp.text

                # Find links containing the registro number
                # Pattern: href="...{registro}...pdf"
                pattern = rf'href=["\']([^"\']*{re.escape(registro)}[^"\']*\.pdf)["\']'
                matches = re.findall(pattern, html, re.IGNORECASE)

                if matches:
                    pdf_path = matches[0]
                    # Make absolute URL
                    if pdf_path.startswith("http"):
                        pdf_url = pdf_path
                    elif pdf_path.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse(page_url)
                        pdf_url = f"{parsed.scheme}://{parsed.netloc}{pdf_path}"
                    else:
                        base = page_url.rsplit("/", 1)[0]
                        pdf_url = f"{base}/{pdf_path}"

                    logger.info("IFU encontrado: %s", pdf_url)
                    return pdf_url

        except Exception as e:
            logger.warning("Erro buscando IFU em %s: %s", page_url, e)

    return None


async def _find_pdf_from_google(registro: str, fabricante: str) -> Optional[str]:
    """Fallback: try to find IFU PDF via web search patterns."""
    # Try common manufacturer website patterns
    fab_lower = (fabricante or "").lower()

    # Extract likely domain name from fabricante
    # e.g., "ORTOSINTESE INDUSTRIA E COMERCIO LTDA" -> "ortosintese"
    words = re.findall(r'[a-záéíóúãõâêô]+', fab_lower)
    if not words:
        return None

    main_name = words[0]  # First word is usually the company name

    # Try common URL patterns
    url_patterns = [
        f"https://www.{main_name}.com.br/images/instrucoes/*{registro}*.pdf",
        f"https://{main_name}.com.br/instrucoes-de-uso",
        f"https://www.{main_name}.com.br/instrucoes-de-uso",
    ]

    async with httpx.AsyncClient(
        headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True
    ) as client:
        for url in url_patterns:
            if "*" in url:
                continue  # Skip glob patterns, just try page scraping

            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue

                html = resp.text
                pattern = rf'href=["\']([^"\']*{re.escape(registro)}[^"\']*\.pdf)["\']'
                matches = re.findall(pattern, html, re.IGNORECASE)

                if matches:
                    pdf_path = matches[0]
                    if pdf_path.startswith("http"):
                        return pdf_path
                    elif pdf_path.startswith("/"):
                        from urllib.parse import urlparse
                        parsed = urlparse(url)
                        return f"{parsed.scheme}://{parsed.netloc}{pdf_path}"
                    else:
                        base = url.rsplit("/", 1)[0]
                        return f"{base}/{pdf_path}"

            except Exception:
                continue

    return None


async def find_ifu_pdf_url(registro: str, fabricante: str) -> Optional[str]:
    """Find the Instructions For Use PDF URL for a product."""
    # Strategy 1: Known manufacturer pages
    url = await _find_pdf_from_manufacturer(registro, fabricante)
    if url:
        return url

    # Strategy 2: Try common URL patterns
    url = await _find_pdf_from_google(registro, fabricante)
    if url:
        return url

    logger.info("IFU PDF não encontrado para registro %s (%s)", registro, fabricante)
    return None


# ── PDF Download & Text Extraction ───────────────────────────────────────

async def download_pdf(url: str) -> Optional[bytes]:
    """Download a PDF from a URL."""
    try:
        async with httpx.AsyncClient(
            headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()

            if len(resp.content) < 1000:
                logger.warning("PDF muito pequeno (%d bytes), ignorando", len(resp.content))
                return None

            return resp.content

    except Exception as e:
        logger.warning("Erro ao baixar PDF %s: %s", url, e)
        return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF."""
    try:
        import fitz  # PyMuPDF — lazy import
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages_text = []
        for page in doc:
            text = page.get_text()
            if text:
                pages_text.append(text)
        doc.close()
        return "\n".join(pages_text)
    except Exception as e:
        logger.warning("Erro ao extrair texto do PDF: %s", e)
        return ""


# ── Section Parsing ──────────────────────────────────────────────────────

def parse_ifu_sections(text: str) -> dict:
    """Parse IFU text into structured sections based on numbered headers."""
    if not text:
        return {}

    # Find all section boundaries
    boundaries = []
    for pattern, section_name in SECTION_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            boundaries.append((match.start(), match.end(), section_name))

    if not boundaries:
        return {}

    # Sort by position
    boundaries.sort(key=lambda x: x[0])

    # Extract text between boundaries
    sections = {}
    for i, (start, end, name) in enumerate(boundaries):
        # Content starts after the header
        content_start = end
        # Content ends at the next section or end of text
        content_end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(text)

        content = text[content_start:content_end].strip()

        # Clean up: remove page headers/footers (Instruções de Uso ...)
        content = re.sub(
            r'Instruções de Uso\s+\d+\s+Fabricante:.*?FL \d+/\d+',
            '', content, flags=re.DOTALL
        )
        content = content.strip()

        if content and len(content) > 10:
            sections[name] = content

    return sections


def _extract_materials(description_text: str) -> str:
    """Extract material/composition info from description section."""
    materials = []

    # Look for material patterns like "CrCoMo ASTM F75", "Polietileno ASTM F648"
    astm_matches = re.findall(
        r'([A-Za-zÀ-ú\s]+(?:ASTM|ISO)\s*[A-Z]?\d+[A-Za-z\-]*)',
        description_text
    )
    if astm_matches:
        materials.extend(m.strip() for m in astm_matches)

    # Look for "matéria prima" or "material" mentions
    mat_matches = re.findall(
        r'(?:mat[eé]ria[- ]prima|material|composi[cç][aã]o)[:\s]+([^\n,;]+)',
        description_text, re.IGNORECASE
    )
    if mat_matches:
        materials.extend(m.strip() for m in mat_matches)

    return "; ".join(set(materials)) if materials else ""


# ── Main Enrichment Function ─────────────────────────────────────────────

async def enrich_product_from_ifu(
    db: AsyncSession,
    product: Product,
) -> dict:
    """
    Enrich a product from its manufacturer's Instructions For Use (IFU) PDF.

    Returns dict with enriched fields, or empty dict if not found.
    Zero AI cost — pure PDF parsing.
    """
    registro = getattr(product, "registro_anvisa", None)
    fabricante = getattr(product, "linha", None)  # 'linha' stores fabricante

    if not registro:
        logger.info("Produto %s sem registro ANVISA, pulando IFU", product.nome)
        return {}

    # 1. Find the PDF URL
    pdf_url = await find_ifu_pdf_url(registro, fabricante or "")
    if not pdf_url:
        return {}

    # 2. Download the PDF
    pdf_bytes = await download_pdf(pdf_url)
    if not pdf_bytes:
        return {}

    # 3. Extract text
    full_text = extract_text_from_pdf(pdf_bytes)
    if not full_text or len(full_text) < 100:
        logger.warning("Texto extraído do PDF muito curto para %s", registro)
        return {}

    # 4. Parse sections
    sections = parse_ifu_sections(full_text)
    if not sections:
        logger.warning("Nenhuma seção encontrada no IFU de %s", registro)
        return {}

    logger.info(
        "IFU parseado para %s: seções encontradas: %s",
        registro, list(sections.keys())
    )

    # 5. Map sections to product fields
    enriched = {}

    # Indicações
    if "indicacoes" in sections:
        enriched["indicacoes"] = sections["indicacoes"]

    # Contraindicações
    if "contraindicacoes" in sections:
        enriched["contraindicacoes"] = sections["contraindicacoes"]

    # Descrição técnica (from Descrição section)
    if "descricao" in sections:
        desc = sections["descricao"]
        # Also try to extract composition/materials info
        materials = _extract_materials(desc)
        if materials:
            desc = f"{desc}\n\nComposição: {materials}"
        enriched["descricao_tecnica"] = desc

    # Diferenciais clínicos — combine riscos + avisos as relevant info
    clinical_parts = []
    if "informacoes_uso" in sections:
        clinical_parts.append(sections["informacoes_uso"])
    if "avisos" in sections:
        clinical_parts.append(sections["avisos"])
    if clinical_parts:
        enriched["diferenciais_clinicos"] = "\n\n".join(clinical_parts)

    # Bula URL
    enriched["bula_url"] = pdf_url

    # 6. Apply enrichment to product (only empty fields)
    updates = {}
    field_map = {
        "descricao_tecnica": "descricao_tecnica",
        "indicacoes": "indicacoes",
        "contraindicacoes": "contraindicacoes",
        "diferenciais_clinicos": "diferenciais_clinicos",
        "bula_url": "bula_url",
    }

    for src_key, db_field in field_map.items():
        new_value = enriched.get(src_key)
        if not new_value:
            continue

        current = getattr(product, db_field, None)
        current_str = str(current).strip() if current else ""
        # Fill empty fields OR overwrite fields that contain model codes
        # (modelos_descricao was initially stored in indicacoes)
        is_model_data = current_str and re.match(r'^[\d/,\s\-]+', current_str[:50])
        if not current_str or len(current_str) < 20 or is_model_data:
            updates[db_field] = new_value

    if updates:
        set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
        updates["product_id"] = str(product.id)
        await db.execute(
            sql_text(f"UPDATE products SET {set_clauses} WHERE id = :product_id"),
            updates,
        )
        await db.commit()

        # Update in-memory object
        for k, v in updates.items():
            if k != "product_id":
                setattr(product, k, v)

        enriched_fields = [k for k in updates if k != "product_id"]
        logger.info(
            "Produto enriquecido via IFU: %s — campos: %s",
            product.nome, ", ".join(enriched_fields),
        )

    return enriched
