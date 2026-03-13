"""
Orquestrador de ETL: executa todos os ETLs em sequência com versionamento e log.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.db.session import AsyncSessionLocal


async def main():
    from scripts.etl.download_tuss import run_etl as tuss_etl
    from scripts.etl.download_rol import run_etl as rol_etl

    print("=" * 60)
    print("OPME Platform - ETL Completo ANS")
    print("=" * 60)

    print("\n--- TUSS 19 (Materiais/OPME) ---")
    try:
        async with AsyncSessionLocal() as db:
            tuss_result = await tuss_etl(db_session=db)
            print(f"TUSS: {tuss_result}")
    except Exception as e:
        print(f"TUSS ERRO: {e}")

    print("\n--- Rol Anexo I (Procedimentos) ---")
    try:
        async with AsyncSessionLocal() as db:
            rol_result = await rol_etl(db_session=db)
            print(f"Rol: {rol_result}")
    except Exception as e:
        print(f"Rol ERRO: {e}")

    print("\n" + "=" * 60)
    print("ETL concluído.")
    print("Nota: DUT requer OPENAI_API_KEY para estruturação LLM.")
    print("Execute parse_dut_pdf.py separadamente com a chave configurada.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
