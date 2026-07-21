"""
ETL: Ingestão em massa do CSV de Produtos para Saúde da Anvisa (Dados Abertos).

Fonte: https://dados.anvisa.gov.br/dados/TA_PRODUTO_SAUDE_SITE.csv
  - ~111k registros, ~27MB, atualizado diariamente
  - Sem autenticação — download direto
  - Separador: ;  |  Encoding: latin-1

Critério 5 do STF (ADI 7.265): Registro ativo na Anvisa é requisito obrigatório.
"""
import asyncio
import csv
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.services.glosa_service import normalize_search  # noqa: E402

ANVISA_CSV_URL = "https://dados.anvisa.gov.br/dados/TA_PRODUTO_SAUDE_SITE.csv"

# Mapeamento das colunas do CSV para nosso modelo
CSV_COLUMNS = {
    "NUMERO_REGISTRO_CADASTRO": "registro",
    "NOME_COMERCIAL": "nome_comercial",
    "DETENTOR_REGISTRO_CADASTRO": "fabricante",
    "CLASSE_RISCO": "classe_risco",
    "VALIDADE_REGISTRO_CADASTRO": "validade_raw",
    "NOME_TECNICO": "nome_tecnico",
    "NOME_FABRICANTE": "nome_fabricante_real",
    "NOME_PAIS_FABRIC": "pais_fabricante",
    "CNPJ_DETENTOR_REGISTRO_CADASTRO": "cnpj_detentor",
    "NUMERO_PROCESSO": "numero_processo",
    "DT_PUB_REGISTRO_CADASTRO": "dt_publicacao",
    "DT_ATUALIZACAO_DADO": "dt_atualizacao",
}


def _parse_validade(raw: str) -> tuple[str, datetime | None]:
    """
    Parseia o campo VALIDADE_REGISTRO_CADASTRO.
    Pode ser 'VIGENTE' (sem data de vencimento) ou uma data como '26/05/2035'.
    Retorna (status, data_validade).
    """
    if not raw or not raw.strip():
        return "desconhecido", None

    raw = raw.strip().upper()

    if raw == "VIGENTE":
        return "ativo", None

    # Tentar parsear como data
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            if dt < datetime.now(timezone.utc):
                return "vencido", dt
            return "ativo", dt
        except ValueError:
            continue

    # Se não é "VIGENTE" nem data, pode ser outro status
    status_map = {
        "CANCELADO": "cancelado",
        "SUSPENSO": "suspenso",
        "VENCIDO": "vencido",
        "CADUCO": "cancelado",
    }
    for key, val in status_map.items():
        if key in raw:
            return val, None

    return "desconhecido", None


def _parse_row(row: dict) -> dict | None:
    """Converte uma linha do CSV para nosso formato de modelo."""
    registro = (row.get("NUMERO_REGISTRO_CADASTRO") or "").strip()
    if not registro:
        return None

    status, data_validade = _parse_validade(
        row.get("VALIDADE_REGISTRO_CADASTRO", "")
    )

    nome_comercial = (row.get("NOME_COMERCIAL") or "").strip() or None
    fabricante = (row.get("DETENTOR_REGISTRO_CADASTRO") or "").strip() or None
    classe_risco = (row.get("CLASSE_RISCO") or "").strip() or None
    nome_tecnico = (row.get("NOME_TECNICO") or "").strip() or None

    # dados_json com todos os campos originais para auditoria
    dados_json = {k: (v or "").strip() for k, v in row.items() if v}

    # Campo de busca sem acento (nome comercial + fabricante + nome técnico)
    search_normalized = normalize_search(
        " ".join(p for p in (nome_comercial, fabricante, nome_tecnico) if p)
    )

    return {
        "registro": registro,
        "nome_comercial": nome_comercial,
        "fabricante": fabricante,
        "status": status,
        "data_validade": data_validade,
        "classe_risco": classe_risco,
        "nome_tecnico": nome_tecnico,
        "dados_json": dados_json,
        "search_normalized": search_normalized,
    }


async def download_csv(progress_callback=None) -> list[dict]:
    """Baixa o CSV da Anvisa e retorna lista de dicts parseados."""
    print(f"[ANVISA CSV] Baixando {ANVISA_CSV_URL}...")

    async with httpx.AsyncClient(
        timeout=120, follow_redirects=True, verify=False
    ) as client:
        resp = await client.get(ANVISA_CSV_URL)
        resp.raise_for_status()

    # CSV usa latin-1 e separador ;
    content = resp.content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(content), delimiter=";")

    rows = []
    seen_registros = set()
    skipped = 0

    for i, raw_row in enumerate(reader):
        parsed = _parse_row(raw_row)
        if not parsed:
            skipped += 1
            continue

        # Deduplicar por registro (manter o mais recente / primeiro encontrado)
        if parsed["registro"] in seen_registros:
            skipped += 1
            continue

        seen_registros.add(parsed["registro"])
        rows.append(parsed)

        if progress_callback and (i + 1) % 10000 == 0:
            progress_callback(f"Parseadas {i + 1} linhas...")

    print(f"[ANVISA CSV] {len(rows)} registros únicos parseados ({skipped} duplicados/inválidos ignorados)")
    return rows


async def run_etl(db_session=None, batch_size: int = 1000):
    """
    ETL principal: baixa CSV da Anvisa e faz upsert em massa na tabela anvisa_products.
    Usa PostgreSQL ON CONFLICT (upsert) para performance máxima.
    """
    rows = await download_csv()

    if not rows:
        print("[ANVISA CSV] Nenhum registro para inserir")
        return {"inserted": 0, "updated": 0, "total": 0}

    if not db_session:
        print(f"[ANVISA CSV] Modo dry-run: {len(rows)} registros parseados")
        for r in rows[:5]:
            print(f"  {r['registro']} | {r['nome_comercial'][:60] if r['nome_comercial'] else 'N/A'} | {r['status']}")
        return {"total": len(rows), "mode": "dry_run"}

    import json as _json
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.db.models import AnvisaProduct, AnvisaStatus

    print(f"[ANVISA CSV] Inserindo {len(rows)} registros no banco (batches de {batch_size})...")

    upserted = 0
    errors = 0
    now = datetime.now(timezone.utc)

    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start:batch_start + batch_size]

        values = []
        for row in batch:
            status_str = row["status"]
            # Garantir que é um status válido do enum
            if status_str not in ("ativo", "vencido", "suspenso", "cancelado"):
                status_str = "ativo"
            values.append({
                "registro": row["registro"],
                "nome_comercial": row["nome_comercial"],
                "fabricante": row["fabricante"],
                "status": status_str,
                "data_validade": row["data_validade"],
                "classe_risco": row["classe_risco"],
                "data_consulta": now,
                "nome_tecnico": row.get("nome_tecnico"),
                "dados_json": row["dados_json"],  # dict nativo → JSON via ORM
                "search_normalized": row.get("search_normalized"),
            })

        try:
            stmt = pg_insert(AnvisaProduct).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["registro"],
                set_={
                    "nome_comercial": stmt.excluded.nome_comercial,
                    "fabricante": stmt.excluded.fabricante,
                    "status": stmt.excluded.status,
                    "data_validade": stmt.excluded.data_validade,
                    "classe_risco": stmt.excluded.classe_risco,
                    "data_consulta": stmt.excluded.data_consulta,
                    "nome_tecnico": stmt.excluded.nome_tecnico,
                    "dados_json": stmt.excluded.dados_json,
                    "search_normalized": stmt.excluded.search_normalized,
                    "updated_at": now,
                },
            )
            await db_session.execute(stmt)
            upserted += len(batch)
        except Exception as e:
            errors += len(batch)
            await db_session.rollback()
            if errors <= batch_size * 3:  # só loga nos primeiros batches com erro
                print(f"  [ERRO batch {batch_start}]: {e}")

        done = min(batch_start + batch_size, len(rows))
        if done % 10000 == 0 or done == len(rows):
            print(f"  [{done}/{len(rows)}] upserted={upserted} erros={errors}")

    await db_session.commit()

    print(f"[ANVISA CSV] Concluído: {upserted} registros upserted, {errors} erros")
    return {"upserted": upserted, "errors": errors, "total": len(rows)}


async def backfill_search_normalized(db_session, batch_size: int = 2000) -> dict:
    """Popula search_normalized nos registros ANVISA já existentes (idempotente).

    Necessário porque o auto-ETL só re-baixa o CSV se a tabela estiver vazia
    (count < 100) — os ~111k registros legados nunca ganhariam o campo de busca
    sem este backfill. Processa apenas linhas com search_normalized NULL, em
    lotes, para não travar em bases grandes.
    """
    from app.db.models import AnvisaProduct

    updated = 0
    while True:
        result = await db_session.execute(
            select(AnvisaProduct)
            .where(AnvisaProduct.search_normalized.is_(None))
            .limit(batch_size)
        )
        batch = result.scalars().all()
        if not batch:
            break
        for ap in batch:
            partes = [p for p in (ap.nome_comercial, ap.fabricante, ap.nome_tecnico) if p]
            # nome_tecnico pode estar só no dados_json em registros antigos
            if not ap.nome_tecnico and isinstance(ap.dados_json, dict):
                nt = (ap.dados_json.get("NOME_TECNICO") or "").strip()
                if nt:
                    partes.append(nt)
            ap.search_normalized = normalize_search(" ".join(partes)) or ""
            updated += 1
        await db_session.commit()
    return {"backfilled": updated}


if __name__ == "__main__":
    asyncio.run(run_etl())
