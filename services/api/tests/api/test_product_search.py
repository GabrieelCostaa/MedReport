"""Busca de produtos: sem acento, multi-campo (nome comercial/técnico/fabricante), status."""
import uuid

import pytest
import pytest_asyncio

from app.db.models import AnvisaProduct
from app.services.glosa_service import normalize_search


def _anvisa(nome, fabricante=None, nome_tecnico=None, status="ativo", registro=None):
    nc, fb, nt = nome, fabricante, nome_tecnico
    return AnvisaProduct(
        id=uuid.uuid4(),
        registro=registro or f"809{uuid.uuid4().hex[:8]}",
        nome_comercial=nc,
        fabricante=fb,
        nome_tecnico=nt,
        status=status,
        classe_risco="III",
        search_normalized=normalize_search(" ".join(p for p in (nc, fb, nt) if p)),
    )


@pytest_asyncio.fixture
async def seed_anvisa(db):
    rows = [
        _anvisa("PRÓTESE TOTAL DE JOELHO", fabricante="Zimmer Biomet"),
        _anvisa("Placa Bloqueada 3.5", fabricante="Synthes", nome_tecnico="OSTEOSSÍNTESE DE FÊMUR"),
        _anvisa("Cateter Vencido", status="vencido"),
    ]
    for r in rows:
        db.add(r)
    await db.commit()
    return rows


class TestProductSearch:
    async def test_accent_insensitive(self, client, auth_headers, seed_anvisa):
        # "protese" sem acento deve achar "PRÓTESE"
        r = await client.get("/api/products", params={"q": "protese"}, headers=auth_headers)
        assert r.status_code == 200
        nomes = [i["nome"] for i in r.json()["items"]]
        assert any("PRÓTESE" in n for n in nomes)

    async def test_multi_word_and(self, client, auth_headers, seed_anvisa):
        r = await client.get("/api/products", params={"q": "protese joelho"}, headers=auth_headers)
        nomes = [i["nome"] for i in r.json()["items"]]
        assert any("PRÓTESE TOTAL DE JOELHO" in n for n in nomes)
        # palavra que não casa junto some
        r2 = await client.get("/api/products", params={"q": "protese cateter"}, headers=auth_headers)
        assert not r2.json()["items"]

    async def test_search_by_nome_tecnico(self, client, auth_headers, seed_anvisa):
        r = await client.get("/api/products", params={"q": "osteossintese"}, headers=auth_headers)
        nomes = [i["nome"] for i in r.json()["items"]]
        assert any("Placa Bloqueada" in n for n in nomes)

    async def test_search_by_fabricante(self, client, auth_headers, seed_anvisa):
        r = await client.get("/api/products", params={"q": "synthes"}, headers=auth_headers)
        nomes = [i["nome"] for i in r.json()["items"]]
        assert any("Placa Bloqueada" in n for n in nomes)

    async def test_status_vencido_hidden(self, client, auth_headers, seed_anvisa):
        r = await client.get("/api/products", params={"q": "cateter"}, headers=auth_headers)
        assert not r.json()["items"]  # vencido não aparece (critério STF)
