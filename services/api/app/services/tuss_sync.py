"""
Sincronização da tabela TUSS a partir da ANS.
Em produção: download do arquivo oficial (ex.: planilha ou XML da ANS).
Aqui: carrega de arquivo local ou URL configurável e upsert no PostgreSQL.
"""
import csv
import io
import logging
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TussTerm

logger = logging.getLogger(__name__)

# URL oficial ANS (exemplo - pode variar)
ANS_TUSS_URL = "https://www.ans.gov.br/prestadores/tiss-troca-de-informacao-de-saude-suplementar"

# Formato esperado: CSV com colunas code, term (ou codigo, descricao)
def parse_tuss_csv(content: str) -> AsyncGenerator[tuple[str, str], None]:
    """Parse CSV com colunas code/term ou codigo/descricao."""
    reader = csv.DictReader(io.StringIO(content))
    for row in reader:
        code = row.get("code") or row.get("codigo") or row.get("cod") or ""
        term = row.get("term") or row.get("descricao") or row.get("termo") or ""
        if code and term:
            yield code.strip(), term.strip()


async def load_tuss_from_file(db: AsyncSession, path: str | Path) -> int:
    """Carrega termos TUSS de um arquivo CSV local. Retorna quantidade inserida/atualizada."""
    path = Path(path)
    if not path.exists():
        logger.warning("TUSS file not found: %s", path)
        return 0
    content = path.read_text(encoding="utf-8", errors="ignore")
    count = 0
    for code, term in parse_tuss_csv(content):
        r = await db.execute(select(TussTerm).where(TussTerm.code == code).limit(1))
        existing = r.scalar_one_or_none()
        if existing:
            existing.term = term
        else:
            db.add(TussTerm(code=code, term=term, table_source="procedimentos"))
        count += 1
    await db.commit()
    logger.info("TUSS sync: %s terms processed from %s", count, path)
    return count


async def sync_tuss_from_ans_url(db: AsyncSession, url: str | None = None) -> int:
    """
    Baixa tabela TUSS da ANS (ou URL configurada) e atualiza o banco.
    Se a ANS mudar o formato, ajustar o parser aqui.
    """
    url = url or ANS_TUSS_URL
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # A ANS pode disponibilizar planilha/XML; exemplo genérico
            resp = await client.get(url)
            resp.raise_for_status()
            # Se for CSV direto:
            if "text/csv" in resp.headers.get("content-type", "") or url.endswith(".csv"):
                return await _upsert_tuss_csv(db, resp.text)
            # Se for Excel/outro, adicionar parser
            logger.warning("TUSS URL content-type not CSV, skipping: %s", resp.headers.get("content-type"))
            return 0
    except Exception as e:
        logger.exception("TUSS sync from URL failed: %s", e)
        return 0


async def _upsert_tuss_csv(db: AsyncSession, content: str) -> int:
    count = 0
    for code, term in parse_tuss_csv(content):
        r = await db.execute(select(TussTerm).where(TussTerm.code == code).limit(1))
        existing = r.scalar_one_or_none()
        if existing:
            existing.term = term
        else:
            db.add(TussTerm(code=code, term=term, table_source="procedimentos"))
        count += 1
    await db.commit()
    return count
