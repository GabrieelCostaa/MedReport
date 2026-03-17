"""
Testes de integração — Products (busca, criação rápida, importação ANVISA).
Testa O QUE os endpoints fazem, não COMO fazem internamente.
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Product, AnvisaProduct, TussMaterial


# ─── GET /api/products ───


@pytest.mark.asyncio
async def test_buscar_produtos_sem_query_deve_retornar_catalogo(
    client: AsyncClient, auth_headers: dict, test_product: Product
):
    resp = await client.get("/api/products", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert items[0]["source"] == "catalog"


@pytest.mark.asyncio
async def test_buscar_produtos_com_query_deve_filtrar_por_nome(
    client: AsyncClient, auth_headers: dict, test_product: Product
):
    resp = await client.get("/api/products?q=Joelho", headers=auth_headers)
    items = resp.json()["items"]
    assert len(items) >= 1
    assert "Joelho" in items[0]["nome"]


@pytest.mark.asyncio
async def test_buscar_produtos_query_sem_resultado_interno_deve_buscar_anvisa(
    client: AsyncClient, auth_headers: dict, test_anvisa_product: AnvisaProduct
):
    resp = await client.get("/api/products?q=Parafuso", headers=auth_headers)
    items = resp.json()["items"]
    # Deve encontrar o produto ANVISA como fallback
    anvisa_items = [i for i in items if i["source"] == "anvisa"]
    assert len(anvisa_items) >= 1
    assert anvisa_items[0]["registro_anvisa"] == test_anvisa_product.registro


@pytest.mark.asyncio
async def test_buscar_produtos_vazio_deve_retornar_lista(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/products?q=produtoinexistentexyz", headers=auth_headers)
    assert resp.status_code == 200
    assert "items" in resp.json()


# ─── POST /api/products (criação rápida) ───


@pytest.mark.asyncio
async def test_criar_produto_rapido_deve_retornar_id_e_nome(
    client: AsyncClient, auth_headers: dict
):
    payload = {
        "nome": "Placa Óssea LCP 4.5mm",
        "registro_anvisa": "80197000050",
        "fabricante": "Synthes",
    }
    resp = await client.post("/api/products", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert body["nome"] == "Placa Óssea LCP 4.5mm"
    uuid.UUID(body["id"])  # Valida UUID


@pytest.mark.asyncio
async def test_criar_produto_com_tuss_mapping_automatico(
    client: AsyncClient, auth_headers: dict, test_tuss_material: TussMaterial
):
    """Se o registro ANVISA tem correspondência na tabela TussMaterial, deve mapear automaticamente."""
    payload = {
        "nome": "Parafuso de Teste",
        "registro_anvisa": test_tuss_material.registro_anvisa,
    }
    resp = await client.post("/api/products", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tuss_mappings"]) >= 1
    assert body["tuss_mappings"][0]["tuss_code"] == test_tuss_material.codigo_tuss


@pytest.mark.asyncio
async def test_criar_produto_sem_nome_deve_retornar_422(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post("/api/products", json={}, headers=auth_headers)
    assert resp.status_code == 422


# ─── POST /api/products/from-anvisa/{registro} ───


@pytest.mark.asyncio
async def test_importar_anvisa_deve_criar_produto_no_catalogo(
    client: AsyncClient, auth_headers: dict,
    test_anvisa_product: AnvisaProduct, test_tuss_material: TussMaterial
):
    resp = await client.post(
        f"/api/products/from-anvisa/{test_anvisa_product.registro}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_exists"] is False
    assert body["registro_anvisa"] == test_anvisa_product.registro
    assert body["nome"] == test_anvisa_product.nome_comercial
    # Deve ter mapeamento TUSS automático
    assert len(body["tuss_mappings"]) >= 1


@pytest.mark.asyncio
async def test_importar_anvisa_produto_ja_existente_deve_retornar_already_exists(
    client: AsyncClient, auth_headers: dict,
    test_anvisa_product: AnvisaProduct, test_tuss_material: TussMaterial
):
    # Primeira importação
    await client.post(
        f"/api/products/from-anvisa/{test_anvisa_product.registro}",
        headers=auth_headers,
    )
    # Segunda importação do mesmo registro
    resp = await client.post(
        f"/api/products/from-anvisa/{test_anvisa_product.registro}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["already_exists"] is True


@pytest.mark.asyncio
async def test_importar_anvisa_registro_inexistente_deve_retornar_404(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/products/from-anvisa/00000000000",
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ─── GET /api/products/{id} ───


@pytest.mark.asyncio
async def test_obter_produto_deve_retornar_detalhes_completos(
    client: AsyncClient, auth_headers: dict, test_product: Product
):
    resp = await client.get(
        f"/api/products/{test_product.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nome"] == test_product.nome
    assert body["registro_anvisa"] == test_product.registro_anvisa
    assert "tuss_mappings" in body


@pytest.mark.asyncio
async def test_obter_produto_inexistente_deve_retornar_404(
    client: AsyncClient, auth_headers: dict
):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/products/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404
