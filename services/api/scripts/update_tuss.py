"""
Job para atualizar tabela TUSS.
Uso:
  cd services/api && PYTHONPATH=. python scripts/update_tuss.py
  ou agendar com cron: 0 2 * * * (diário 2h)
"""
import asyncio
import os
import sys

# repo root -> services/api
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import AsyncSessionLocal
from app.db.init_db import create_tables
from app.services.tuss_sync import load_tuss_from_file, sync_tuss_from_ans_url


async def main():
    await create_tables()
    data_file = os.path.join(os.path.dirname(__file__), "tuss_sample.csv")
    async with AsyncSessionLocal() as db:
        n = await load_tuss_from_file(db, data_file)
        if n == 0:
            # tentar URL (pode falhar se ANS não retornar CSV)
            n = await sync_tuss_from_ans_url(db)
        print(f"TUSS update: {n} terms processed.")


if __name__ == "__main__":
    asyncio.run(main())
