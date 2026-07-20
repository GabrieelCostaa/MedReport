"""ETL da TISS Tabela 38 (motivos de glosa) a partir do CSV versionado no repo.

Sem rede: lê data/ans/tabela38_motivos_glosa.csv (gerado 1x por
scripts/etl/extract_tabela38.py) e faz upsert em glosa_motivos.
Seguro para rodar no Render free tier e no auto-ETL de startup.

Uso:
    python scripts/etl/ingest_tabela38.py          # dry-run (só parse)
    via ingest_all.py / auto-ETL                   # ingestão real
"""
import asyncio
import csv
import io
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.etl.download_tuss import normalize_text  # noqa: E402

logger = logging.getLogger(__name__)

TABELA38_CSV_PATH = (
    Path(__file__).resolve().parent.parent.parent / "data" / "ans" / "tabela38_motivos_glosa.csv"
)
VERSAO_TISS = "202601"


def _parse_date(value: str) -> datetime | None:
    """Aceita "", "YYYY-MM-DD" ou "YYYY-MM-DD HH:MM:SS"."""
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def parse_tabela38_csv(content: str) -> list[dict]:
    """Parser puro (testável, sem rede/DB) do CSV codigo;descricao;vigencia_inicio;vigencia_fim."""
    records: list[dict] = []
    now = datetime.now(timezone.utc)
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    for row in reader:
        codigo = (row.get("codigo") or "").strip()
        descricao = (row.get("descricao") or "").strip()
        if not codigo or not descricao:
            continue
        vig_fim = _parse_date(row.get("vigencia_fim", ""))
        records.append({
            "codigo": codigo,
            "descricao": descricao,
            "descricao_normalized": normalize_text(descricao),
            "vigencia_inicio": _parse_date(row.get("vigencia_inicio", "")),
            "vigencia_fim": vig_fim,
            "ativo": vig_fim is None or vig_fim > now,
            "versao_tiss": VERSAO_TISS,
            "raw_data": dict(row),
        })
    return records


async def ingest_glosa_motivos(db_session, records: list[dict]) -> dict:
    """Upsert por codigo (espelho de ingest_tuss_materials — SQLite e Postgres)."""
    from sqlalchemy import select
    from app.db.models import GlosaMotivo

    inserted = updated = 0
    for rec in records:
        result = await db_session.execute(
            select(GlosaMotivo).where(GlosaMotivo.codigo == rec["codigo"])
        )
        existing = result.scalar_one_or_none()
        if existing:
            for field, value in rec.items():
                setattr(existing, field, value)
            updated += 1
        else:
            db_session.add(GlosaMotivo(**rec))
            inserted += 1
    await db_session.commit()
    return {"inserted": inserted, "updated": updated, "total": len(records)}


async def run_etl(db_session=None) -> dict:
    if not TABELA38_CSV_PATH.exists():
        raise FileNotFoundError(
            f"{TABELA38_CSV_PATH} não existe. Gere-o com: python scripts/etl/extract_tabela38.py "
            "(requer o pacote TISS em data/ans/tiss/)"
        )

    raw = TABELA38_CSV_PATH.read_bytes()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        content = raw.decode("latin-1")

    records = parse_tabela38_csv(content)
    logger.info("Tabela 38: %d motivos de glosa parseados", len(records))

    if db_session is None:
        return {"parsed": len(records)}

    stats = await ingest_glosa_motivos(db_session, records)
    logger.info("Tabela 38 ingerida: %s", stats)
    return stats


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(run_etl()))
