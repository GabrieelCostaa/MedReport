"""
Testes do endpoint GET /api/ai/evidences-preview via HTTP.
Requer: API rodando em localhost:8000
Uso: cd services/api && python scripts/test_evidences_preview.py
"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(str(Path(__file__).resolve().parent.parent))

import httpx

API_BASE = "http://localhost:8000"
LOGIN_EMAIL = "medico@opme.com"
LOGIN_PASSWORD = "senha123"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []


def report(name: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    results.append((name, ok))
    msg = f"  [{status}] {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)


async def get_token() -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{API_BASE}/api/auth/login",
            data={"username": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        )
        if resp.status_code == 200:
            return resp.json().get("access_token", "")
    return ""


async def test_preview_cid_com_evidencias_internas(token: str):
    """CID E88.2 (Lipedema) deve ter evidências internas."""
    print("\n=== test_preview_cid_com_evidencias_internas ===")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/api/ai/evidences-preview",
            params={"cid": "E88.2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        report("status 200", resp.status_code == 200, f"got {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            report("retorna CID", data.get("cid") == "E88.2")
            report("internal_count >= 0", data.get("internal_count", -1) >= 0, str(data.get("internal_count")))
            report("pubmed_count >= 0", data.get("pubmed_count", -1) >= 0, str(data.get("pubmed_count")))
            report("total_count >= 0", data.get("total_count", -1) >= 0, str(data.get("total_count")))
            report("tem preview list", isinstance(data.get("preview"), list))


async def test_preview_cid_sem_evidencias_internas(token: str):
    """CID M16.1 (quadril) provavelmente sem evidências internas, mas com PubMed."""
    print("\n=== test_preview_cid_sem_evidencias_internas ===")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/api/ai/evidences-preview",
            params={"cid": "M16.1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        report("status 200", resp.status_code == 200, f"got {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            report("pubmed_count > 0 (PubMed encontrou)", data.get("pubmed_count", 0) > 0, str(data.get("pubmed_count")))
            if data.get("preview"):
                ev = data["preview"][0]
                report("preview tem autor", bool(ev.get("autor")))
                report("preview tem ano", bool(ev.get("ano")))
                report("preview tem tipo", bool(ev.get("tipo")))


async def test_preview_cid_invalido(token: str):
    """CID inválido deve retornar 0 sem erro."""
    print("\n=== test_preview_cid_invalido ===")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/api/ai/evidences-preview",
            params={"cid": "XXXXX"},
            headers={"Authorization": f"Bearer {token}"},
        )
        report("status 200 (não dá erro)", resp.status_code == 200, f"got {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            report("total_count = 0", data.get("total_count", -1) == 0, str(data.get("total_count")))


async def test_preview_sem_auth():
    """Sem token deve retornar 401 ou 403."""
    print("\n=== test_preview_sem_auth ===")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{API_BASE}/api/ai/evidences-preview",
            params={"cid": "M17.0"},
        )
        report("sem auth retorna 401/403", resp.status_code in (401, 403), f"got {resp.status_code}")


async def test_preview_cid_curto(token: str):
    """CID muito curto retorna vazio sem erro."""
    print("\n=== test_preview_cid_curto ===")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{API_BASE}/api/ai/evidences-preview",
            params={"cid": "M"},
            headers={"Authorization": f"Bearer {token}"},
        )
        report("status 200", resp.status_code == 200, f"got {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            report("total_count = 0 para CID curto", data.get("total_count", -1) == 0)


async def main():
    print("=" * 60)
    print("TESTES DO ENDPOINT — /api/ai/evidences-preview")
    print("=" * 60)

    token = await get_token()
    if not token:
        print("\n[ERRO] Não conseguiu fazer login. API rodando?")
        return False

    print(f"  Token obtido: {token[:20]}...")

    start = time.time()
    await test_preview_sem_auth()
    await test_preview_cid_curto(token)
    await test_preview_cid_com_evidencias_internas(token)
    await test_preview_cid_sem_evidencias_internas(token)
    await test_preview_cid_invalido(token)
    elapsed = time.time() - start

    print("\n" + "=" * 60)
    passed = sum(1 for _, ok in results if ok)
    failed = sum(1 for _, ok in results if not ok)
    print(f"TOTAL: {passed} passed, {failed} failed ({elapsed:.1f}s)")
    if failed:
        print("\nFALHAS:")
        for name, ok in results:
            if not ok:
                print(f"  - {name}")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
