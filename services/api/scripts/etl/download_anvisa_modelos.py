"""
ETL: Enriquecimento da tabela anvisa_products com dados do CSV de Modelos.

Fonte: https://dados.anvisa.gov.br/dados/TA_PRODUTO_SAUDE_MODELO.csv
  - ~3.7M linhas (1 por modelo/apresentação por registro)
  - Sem autenticação — download direto
  - Separador: ;  |  Encoding: latin-1

Adiciona:
  - nome_tecnico: Nome técnico padronizado (ex: "PARAFUSO ÓSSEO ORTOPÉDICO")
  - modelos_descricao: Modelos/apresentações agregados por registro (até 20)
"""
import asyncio
import csv
import io
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Alguns registros têm campos enormes (lista de modelos concatenada)
csv.field_size_limit(10 * 1024 * 1024)  # 10MB

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ANVISA_MODELO_URL = "https://dados.anvisa.gov.br/dados/TA_PRODUTO_SAUDE_MODELO.csv"

MAX_MODELOS_PER_REGISTRO = 20
MAX_MODELOS_CHARS = 5000


def _aggregate_modelos(rows_iter) -> dict:
    """Agrega modelos por registro. Retorna dict[registro] -> {nome_tecnico, modelos}."""
    aggregated = {}
    total_rows = 0
    skipped = 0

    for raw_row in rows_iter:
        total_rows += 1
        registro = (raw_row.get("NUMERO_REGISTRO_CADASTRO") or "").strip()
        if not registro:
            skipped += 1
            continue

        modelo = (raw_row.get("DS_MODELO_PRODUTO_MEDICO") or "").strip()
        nome_tecnico = (raw_row.get("NOME_TECNICO") or "").strip()

        if registro not in aggregated:
            aggregated[registro] = {
                "nome_tecnico": nome_tecnico,
                "modelos": [],
                "modelos_chars": 0,
            }

        entry = aggregated[registro]

        # Atualizar nome_tecnico se vazio
        if not entry["nome_tecnico"] and nome_tecnico:
            entry["nome_tecnico"] = nome_tecnico

        # Agregar modelo (com limites)
        if (
            modelo
            and len(entry["modelos"]) < MAX_MODELOS_PER_REGISTRO
            and entry["modelos_chars"] < MAX_MODELOS_CHARS
        ):
            entry["modelos"].append(modelo)
            entry["modelos_chars"] += len(modelo)

        if total_rows % 500000 == 0:
            print(f"  [{total_rows}] registros únicos: {len(aggregated)}")

    print(
        f"[ANVISA MODELOS] {total_rows} linhas processadas → "
        f"{len(aggregated)} registros únicos ({skipped} inválidos)"
    )
    return aggregated


async def download_and_aggregate(progress_callback=None) -> dict:
    """Baixa o CSV de Modelos e agrega por registro."""
    print(f"[ANVISA MODELOS] Baixando {ANVISA_MODELO_URL}...")
    print("  (arquivo grande ~3.7M linhas, pode demorar)...")

    async with httpx.AsyncClient(
        timeout=600, follow_redirects=True, verify=False
    ) as client:
        resp = await client.get(ANVISA_MODELO_URL)
        resp.raise_for_status()

    print(f"[ANVISA MODELOS] Download completo ({len(resp.content) / 1024 / 1024:.1f} MB)")

    content = resp.content.decode("latin-1")
    reader = csv.DictReader(io.StringIO(content), delimiter=";")

    return _aggregate_modelos(reader)


async def run_etl(db_session=None, batch_size: int = 1000):
    """
    ETL: baixa CSV de Modelos, agrega por registro, e atualiza anvisa_products.
    Adiciona nome_tecnico e modelos_descricao via UPDATE.
    """
    aggregated = await download_and_aggregate()

    if not aggregated:
        print("[ANVISA MODELOS] Nenhum registro para atualizar")
        return {"updated": 0, "total": 0}

    if not db_session:
        print(f"[ANVISA MODELOS] Modo dry-run: {len(aggregated)} registros")
        for reg, data in list(aggregated.items())[:5]:
            modelos_str = "; ".join(data["modelos"][:3])
            print(f"  {reg} | {data['nome_tecnico'][:60]} | {len(data['modelos'])} modelos")
            print(f"    Ex: {modelos_str[:100]}...")
        return {"total": len(aggregated), "mode": "dry_run"}

    from sqlalchemy import text as sql_text

    # Garantir que as colunas existem
    for col, col_type in [
        ("nome_tecnico", "VARCHAR(500)"),
        ("modelos_descricao", "TEXT"),
    ]:
        try:
            await db_session.execute(
                sql_text(f"ALTER TABLE anvisa_products ADD COLUMN {col} {col_type}")
            )
            await db_session.commit()
            print(f"  Coluna anvisa_products.{col} criada")
        except Exception:
            await db_session.rollback()

    print(f"[ANVISA MODELOS] Atualizando {len(aggregated)} registros...")

    updated = 0
    not_found = 0
    errors = 0

    registros = list(aggregated.items())

    for batch_start in range(0, len(registros), batch_size):
        batch = registros[batch_start:batch_start + batch_size]

        for registro, data in batch:
            modelos_text = "; ".join(data["modelos"])
            if len(modelos_text) > MAX_MODELOS_CHARS:
                modelos_text = modelos_text[:MAX_MODELOS_CHARS] + "..."

            try:
                result = await db_session.execute(
                    sql_text(
                        "UPDATE anvisa_products "
                        "SET nome_tecnico = :nome_tecnico, "
                        "    modelos_descricao = :modelos, "
                        "    updated_at = :now "
                        "WHERE registro = :registro"
                    ),
                    {
                        "registro": registro,
                        "nome_tecnico": data["nome_tecnico"] or None,
                        "modelos": modelos_text or None,
                        "now": datetime.now(timezone.utc),
                    },
                )
                if result.rowcount > 0:
                    updated += 1
                else:
                    not_found += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  [ERRO] {registro}: {e}")

        await db_session.commit()

        done = min(batch_start + batch_size, len(registros))
        if done % 10000 == 0 or done == len(registros):
            print(f"  [{done}/{len(registros)}] updated={updated} not_found={not_found} errors={errors}")

    print(
        f"[ANVISA MODELOS] Concluído: {updated} atualizados, "
        f"{not_found} não encontrados na base, {errors} erros"
    )
    return {
        "updated": updated,
        "not_found": not_found,
        "errors": errors,
        "total": len(aggregated),
    }


if __name__ == "__main__":
    asyncio.run(run_etl())
