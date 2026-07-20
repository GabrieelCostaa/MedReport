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
    from scripts.etl.download_anvisa import run_etl as anvisa_etl

    print("=" * 60)
    print("OPME Platform - ETL Completo ANS + Anvisa")
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

    print("\n--- Anvisa Produtos para Saúde (CSV Dados Abertos) ---")
    try:
        async with AsyncSessionLocal() as db:
            anvisa_result = await anvisa_etl(db_session=db)
            print(f"Anvisa: {anvisa_result}")
    except Exception as e:
        print(f"Anvisa ERRO: {e}")

    print("\n--- Anvisa Modelos/Apresentações (enriquecimento) ---")
    try:
        from scripts.etl.download_anvisa_modelos import run_etl as modelos_etl
        async with AsyncSessionLocal() as db:
            modelos_result = await modelos_etl(db_session=db)
            print(f"Modelos: {modelos_result}")
    except Exception as e:
        print(f"Modelos ERRO: {e}")

    print("\n--- TISS Tabela 38 (Motivos de Glosa — arquivo do repo) ---")
    try:
        from scripts.etl.ingest_tabela38 import run_etl as tabela38_etl
        async with AsyncSessionLocal() as db:
            print(f"Tabela 38: {await tabela38_etl(db_session=db)}")
    except Exception as e:
        print(f"Tabela 38 ERRO: {e}")

    print("\n--- Painel de Glosas ANS (PDA-057, por operadora) ---")
    try:
        from scripts.etl.download_glosa_panel import run_etl as glosa_panel_etl
        async with AsyncSessionLocal() as db:
            print(f"Painel Glosas: {await glosa_panel_etl(db_session=db)}")
    except Exception as e:
        print(f"Painel Glosas ERRO: {e}")

    print("\n" + "=" * 60)
    print("ETL concluído.")
    print("Nota: DUT requer OPENAI_API_KEY para estruturação LLM.")
    print("Execute parse_dut_pdf.py separadamente com a chave configurada.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
