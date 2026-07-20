"""ETL do Painel de Indicadores de Glosa da ANS (dados abertos PDA-057).

5 CSVs por operadora × mês (desde 2019): % glosa inicial, % glosa final,
tempo médio de pagamento, nº e valor de guias sem retorno >60 dias.
~1,7 MB cada — seguro para o Render free tier.

Robustez (dados da ANS têm surpresas — o header oficial traz o typo
"PC_GLOSA_INCIAL"):
- a coluna de valor é detectada POR EXCLUSÃO das colunas meta, nunca por nome;
- contrato validado ANTES de qualquer escrita (ContractError aborta só o
  arquivo fora do padrão, os demais seguem);
- ingestão é um full-refresh ATÔMICO: só após os 5 arquivos parseados e
  mesclados, uma única transação faz delete+insert — em qualquer erro, o
  snapshot anterior sobrevive intacto.

Uso:
    python scripts/etl/download_glosa_panel.py     # dry-run (download + parse)
    via ingest_all.py / auto-ETL                   # ingestão real
"""
import asyncio
import csv
import io
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.glosa_service import normalize_search  # noqa: E402

logger = logging.getLogger(__name__)

GLOSA_PANEL_BASE_URL = "https://dadosabertos.ans.gov.br/FTP/PDA/painel_de_glosas-057/dados/"

# sufixo do arquivo → coluna do modelo OperadoraGlosaIndicador
INDICATOR_FILES = {
    "percentual_glosa_inicial": "pc_glosa_inicial",
    "percentual_glosa_final": "pc_glosa_final",
    "tempo_medio_pagamento": "tempo_medio_pagamento_dias",
    "numero_guias_sem_retorno": "numero_guias_sem_retorno",
    "valor_guias_sem_retorno": "valor_guias_sem_retorno",
}

META_COLUMNS = {
    "REGISTRO_OPERADORA", "NM_RAZAO_SOCIAL_OPERADORA", "DE_PORTE_OPERADORA",
    "NM_SEGMENTACAO_OPERADORA", "NM_MODALIDADE_OPERADORA",
    "CD_PERIODO", "CD_INDICADOR", "DT_CARGA",
}
REQUIRED_META = {"REGISTRO_OPERADORA", "CD_PERIODO"}

_PERIODO_RE = re.compile(r"^\d{4}-\d{2}$")


class ContractError(Exception):
    """O CSV não obedece ao contrato esperado — arquivo abortado, dado antigo preservado."""


async def download_csv(url: str) -> bytes:
    import httpx
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_decimal(value: str) -> float | None:
    """"17,08" → 17.08; "1.234,56" → 1234.56; ""/"-" → None."""
    value = (value or "").strip().strip('"')
    if not value or value == "-":
        return None
    value = value.replace(".", "").replace(",", ".") if "," in value else value
    try:
        return float(value)
    except ValueError:
        return None


def parse_glosa_csv(content: str, target_column: str) -> list[dict]:
    """Parser puro de um CSV do painel. Valida o contrato antes de devolver linhas.

    A coluna de valor é a ÚNICA fora de META_COLUMNS (o nome oficial tem typo
    "PC_GLOSA_INCIAL", então nunca casamos por nome).
    """
    reader = csv.DictReader(io.StringIO(content), delimiter=";", quotechar='"')
    headers = set(reader.fieldnames or [])

    missing = REQUIRED_META - headers
    if missing:
        raise ContractError(f"colunas meta obrigatórias ausentes: {sorted(missing)}")

    value_columns = headers - META_COLUMNS
    if len(value_columns) != 1:
        raise ContractError(
            f"esperada exatamente 1 coluna de valor fora das meta; encontradas: {sorted(value_columns)}"
        )
    value_column = value_columns.pop()

    records: list[dict] = []
    for row in reader:
        registro = (row.get("REGISTRO_OPERADORA") or "").strip()
        periodo = (row.get("CD_PERIODO") or "").strip()
        if not registro or not _PERIODO_RE.match(periodo):
            continue
        razao = (row.get("NM_RAZAO_SOCIAL_OPERADORA") or "").strip()
        records.append({
            "registro_ans": registro,
            "razao_social": razao,
            "razao_social_normalized": normalize_search(razao),
            "porte": (row.get("DE_PORTE_OPERADORA") or "").strip(),
            "segmentacao": (row.get("NM_SEGMENTACAO_OPERADORA") or "").strip(),
            "modalidade": (row.get("NM_MODALIDADE_OPERADORA") or "").strip(),
            "periodo": periodo,
            "dt_carga": (row.get("DT_CARGA") or "").strip(),
            target_column: parse_decimal(row.get(value_column, "")),
        })
    return records


def merge_indicator_records(per_indicator: dict[str, list[dict]]) -> list[dict]:
    """Mescla os 5 arquivos por (registro_ans, periodo) em uma linha com as 5 colunas."""
    merged: dict[tuple[str, str], dict] = {}
    for column, records in per_indicator.items():
        for rec in records:
            key = (rec["registro_ans"], rec["periodo"])
            if key not in merged:
                merged[key] = {k: v for k, v in rec.items() if k != column}
                for col in INDICATOR_FILES.values():
                    merged[key].setdefault(col, None)
            merged[key][column] = rec[column]
    return list(merged.values())


async def ingest_glosa_panel(db_session, merged: list[dict]) -> dict:
    """Full-refresh atômico: delete + insert em chunks numa transação única.

    O dataset é um snapshot completo (~56k linhas); upsert linha a linha seria
    lento demais em Postgres remoto (Neon). delete+insert é portável
    (sem ON CONFLICT) e o rollback preserva o snapshot anterior em caso de erro.
    """
    from sqlalchemy import delete
    from app.db.models import OperadoraGlosaIndicador

    CHUNK = 1000
    try:
        await db_session.execute(delete(OperadoraGlosaIndicador))
        for i in range(0, len(merged), CHUNK):
            db_session.add_all(
                OperadoraGlosaIndicador(**rec) for rec in merged[i:i + CHUNK]
            )
            await db_session.flush()
        await db_session.commit()
    except Exception:
        await db_session.rollback()
        raise
    return {"loaded": len(merged)}


async def run_etl(db_session=None) -> dict:
    per_indicator: dict[str, list[dict]] = {}
    files_ok, files_failed = [], []

    for suffix, column in INDICATOR_FILES.items():
        url = f"{GLOSA_PANEL_BASE_URL}pda-057-painel_de_glosas-{suffix}.csv"
        try:
            raw = await download_csv(url)
            records = parse_glosa_csv(decode_bytes(raw), column)
            per_indicator[column] = records
            files_ok.append(suffix)
            logger.info("Painel glosas: %s → %d linhas", suffix, len(records))
        except ContractError as e:
            files_failed.append(suffix)
            logger.error("Painel glosas: %s FORA DO CONTRATO (%s) — arquivo ignorado", suffix, e)
        except Exception as e:
            files_failed.append(suffix)
            logger.error("Painel glosas: falha ao baixar/parsear %s: %s", suffix, e)

    if not per_indicator:
        raise RuntimeError(f"Nenhum arquivo do painel de glosas utilizável (falhas: {files_failed})")

    merged = merge_indicator_records(per_indicator)
    result = {"files_ok": files_ok, "files_failed": files_failed, "merged_rows": len(merged)}

    if db_session is None:
        return result

    result.update(await ingest_glosa_panel(db_session, merged))
    logger.info("Painel de glosas carregado: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(run_etl()))
