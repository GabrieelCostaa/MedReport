"""
ETL: Download e ingestão da TUSS 19 (Materiais e OPME) do FTP da ANS.

Fonte da verdade: https://dadosabertos.ans.gov.br/FTP/PDA/terminologia_unificada_saude_suplementar_TUSS/
Estratégia: Verifica Last-Modified -> baixa ZIP -> extrai CSV -> parseia Tabela 19 -> upsert no banco.
"""
import asyncio
import csv
import hashlib
import io
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import select, text

TUSS_FTP_URL = "https://dadosabertos.ans.gov.br/FTP/PDA/terminologia_unificada_saude_suplementar_TUSS/TUSS.zip"
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ans"


def normalize_text(value: str) -> str:
    """Normaliza texto para busca: lowercase, sem acentos extras, trim."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.strip().lower())


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def check_last_modified(url: str = TUSS_FTP_URL) -> str | None:
    """Verifica o header Last-Modified do ZIP sem baixar o arquivo."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.head(url)
        return resp.headers.get("Last-Modified")


async def download_tuss_zip(url: str = TUSS_FTP_URL) -> bytes:
    """Baixa o TUSS.zip completo."""
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def extract_table_19_from_zip(zip_bytes: bytes) -> list[dict]:
    """Extrai CSV da Tabela 19 (Materiais/OPME) do ZIP e retorna lista de dicts."""
    records = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_candidates = [
            n for n in zf.namelist()
            if n.endswith(".csv") and ("19" in n.lower() or "material" in n.lower() or "opme" in n.lower())
        ]
        if not csv_candidates:
            csv_candidates = [n for n in zf.namelist() if n.endswith(".csv")]

        for csv_name in csv_candidates:
            raw = zf.read(csv_name)
            for encoding in ("utf-8", "latin-1", "cp1252"):
                try:
                    text_content = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                text_content = raw.decode("latin-1", errors="replace")

            reader = csv.DictReader(io.StringIO(text_content), delimiter=";")
            for row in reader:
                code = (row.get("CD_PROCEDIMENTO") or row.get("CODIGO") or
                        row.get("cd_procedimento") or row.get("codigo") or "").strip()
                name = (row.get("DS_PROCEDIMENTO") or row.get("DESCRICAO") or row.get("TERMO") or
                        row.get("ds_procedimento") or row.get("descricao") or row.get("termo") or "").strip()
                if not code or not name:
                    continue

                grupo = (row.get("GRUPO") or row.get("grupo") or "").strip()
                subgrupo = (row.get("SUBGRUPO") or row.get("subgrupo") or "").strip()

                records.append({
                    "codigo_tuss": code,
                    "nome": name,
                    "display_normalized": normalize_text(name),
                    "grupo": grupo or None,
                    "subgrupo": subgrupo or None,
                    "fabricante": None,
                    "manufacturer_normalized": None,
                    "registro_anvisa": None,
                    "descricao": None,
                    "ativo": True,
                    "raw_data": {k: v for k, v in row.items() if v},
                })
    return records


def parse_tuss_csv_content(content: str, delimiter: str = ";") -> list[dict]:
    """Parseia conteúdo CSV da TUSS diretamente (para testes com fixtures)."""
    records = []
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    for row in reader:
        code = (row.get("CD_PROCEDIMENTO") or row.get("CODIGO") or
                row.get("cd_procedimento") or row.get("codigo") or "").strip()
        name = (row.get("DS_PROCEDIMENTO") or row.get("DESCRICAO") or row.get("TERMO") or
                row.get("ds_procedimento") or row.get("descricao") or row.get("termo") or "").strip()
        if not code or not name:
            continue
        records.append({
            "codigo_tuss": code,
            "nome": name,
            "display_normalized": normalize_text(name),
            "grupo": (row.get("GRUPO") or row.get("grupo") or "").strip() or None,
            "subgrupo": (row.get("SUBGRUPO") or row.get("subgrupo") or "").strip() or None,
            "fabricante": None,
            "manufacturer_normalized": None,
            "registro_anvisa": None,
            "descricao": None,
            "ativo": True,
            "raw_data": {k: v for k, v in row.items() if v},
        })
    return records


async def ingest_tuss_materials(db_session, records: list[dict], versao: str) -> dict:
    """Upsert de materiais TUSS no banco. Idempotente."""
    from app.db.models import TussMaterial

    inserted = 0
    updated = 0
    for rec in records:
        existing = await db_session.execute(
            select(TussMaterial).where(TussMaterial.codigo_tuss == rec["codigo_tuss"])
        )
        existing = existing.scalar_one_or_none()
        if existing:
            existing.nome = rec["nome"]
            existing.display_normalized = rec["display_normalized"]
            existing.grupo = rec["grupo"]
            existing.subgrupo = rec["subgrupo"]
            existing.versao_tuss = versao
            existing.raw_data = rec["raw_data"]
            existing.data_atualizacao = datetime.utcnow()
            updated += 1
        else:
            material = TussMaterial(
                **rec,
                versao_tuss=versao,
                data_atualizacao=datetime.utcnow(),
            )
            db_session.add(material)
            inserted += 1

    await db_session.commit()
    return {"inserted": inserted, "updated": updated, "total": len(records)}


async def run_etl(db_session=None):
    """Executa ETL completo: download, parse, ingestão."""
    print("[TUSS ETL] Verificando Last-Modified...")
    last_modified = await check_last_modified()
    print(f"[TUSS ETL] Last-Modified: {last_modified}")

    print("[TUSS ETL] Baixando TUSS.zip...")
    zip_bytes = await download_tuss_zip()
    sha = compute_sha256(zip_bytes)
    print(f"[TUSS ETL] ZIP baixado: {len(zip_bytes)} bytes, SHA256: {sha[:16]}...")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DATA_DIR / "TUSS.zip"
    zip_path.write_bytes(zip_bytes)

    print("[TUSS ETL] Extraindo Tabela 19...")
    records = extract_table_19_from_zip(zip_bytes)
    print(f"[TUSS ETL] {len(records)} registros encontrados")

    if db_session:
        versao = last_modified or datetime.utcnow().strftime("%Y%m%d")
        result = await ingest_tuss_materials(db_session, records, versao)
        print(f"[TUSS ETL] Resultado: {result}")
        return result

    return {"records_parsed": len(records), "sha256": sha}


if __name__ == "__main__":
    asyncio.run(run_etl())
