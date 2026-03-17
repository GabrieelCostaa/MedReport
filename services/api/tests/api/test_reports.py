"""
Testes de integração — Reports (CRUD, sign, review, pagination).
Testa O QUE os endpoints fazem, não COMO fazem internamente.
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User, Report, TussTerm
from tests.api.conftest import TEST_PASSWORD


REPORT_PAYLOAD = {
    "cid": "M17.1",
    "diagnosis": "Gonartrose primária bilateral",
    "surgery_description": "Artroplastia total de joelho direito",
    "materials": "Prótese de joelho cimentada",
    "health_plan": "Unimed",
}


# ─── POST /api/reports ───


@pytest.mark.asyncio
async def test_criar_relatorio_deve_retornar_id(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post("/api/reports", json=REPORT_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    # UUID válido
    uuid.UUID(body["id"])


@pytest.mark.asyncio
async def test_criar_relatorio_campos_opcionais_ausentes(
    client: AsyncClient, auth_headers: dict
):
    payload = {
        "cid": "S72.0",
        "diagnosis": "Fratura do colo do fêmur",
        "surgery_description": "Osteossíntese com DHS",
    }
    resp = await client.post("/api/reports", json=payload, headers=auth_headers)
    assert resp.status_code == 200
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_criar_relatorio_sem_campos_obrigatorios_deve_retornar_422(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post("/api/reports", json={"cid": "M17.1"}, headers=auth_headers)
    assert resp.status_code == 422


# ─── GET /api/reports ───


@pytest.mark.asyncio
async def test_listar_relatorios_vazio_deve_retornar_lista_vazia(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.get("/api/reports", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["page"] == 1


@pytest.mark.asyncio
async def test_listar_relatorios_deve_retornar_criados(
    client: AsyncClient, auth_headers: dict
):
    # Cria 3 relatórios
    for i in range(3):
        await client.post(
            "/api/reports",
            json={**REPORT_PAYLOAD, "diagnosis": f"Diagnóstico {i}"},
            headers=auth_headers,
        )

    resp = await client.get("/api/reports", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3


@pytest.mark.asyncio
async def test_paginacao_deve_respeitar_per_page(
    client: AsyncClient, auth_headers: dict
):
    for _ in range(5):
        await client.post("/api/reports", json=REPORT_PAYLOAD, headers=auth_headers)

    resp = await client.get("/api/reports?page=1&per_page=2", headers=auth_headers)
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["total_pages"] == 3

    # Página 3 deve ter 1 item
    resp2 = await client.get("/api/reports?page=3&per_page=2", headers=auth_headers)
    assert len(resp2.json()["items"]) == 1


# ─── GET /api/reports/{id} ───


@pytest.mark.asyncio
async def test_obter_relatorio_deve_retornar_dados_completos(
    client: AsyncClient, auth_headers: dict
):
    create_resp = await client.post("/api/reports", json=REPORT_PAYLOAD, headers=auth_headers)
    report_id = create_resp.json()["id"]

    resp = await client.get(f"/api/reports/{report_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["cid"] == "M17.1"
    assert body["diagnosis"] == REPORT_PAYLOAD["diagnosis"]
    assert body["status"] == "draft"


@pytest.mark.asyncio
async def test_obter_relatorio_inexistente_deve_retornar_404(
    client: AsyncClient, auth_headers: dict
):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/reports/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


# ─── POST /api/reports/{id}/sign ───


@pytest.mark.asyncio
async def test_assinar_relatorio_deve_mudar_status_para_signed(
    client: AsyncClient, auth_headers: dict
):
    create_resp = await client.post("/api/reports", json=REPORT_PAYLOAD, headers=auth_headers)
    report_id = create_resp.json()["id"]

    sign_resp = await client.post(f"/api/reports/{report_id}/sign", headers=auth_headers)
    assert sign_resp.status_code == 200

    # Verifica que o status mudou
    get_resp = await client.get(f"/api/reports/{report_id}", headers=auth_headers)
    assert get_resp.json()["status"] == "signed"


@pytest.mark.asyncio
async def test_assinar_relatorio_inexistente_deve_retornar_404(
    client: AsyncClient, auth_headers: dict
):
    fake_id = str(uuid.uuid4())
    resp = await client.post(f"/api/reports/{fake_id}/sign", headers=auth_headers)
    assert resp.status_code == 404


# ─── POST /api/reports/review/text ───


@pytest.mark.asyncio
async def test_review_texto_com_codigo_tuss_valido_sem_inconsistencias(
    client: AsyncClient, auth_headers: dict, test_tuss_term: TussTerm
):
    resp = await client.post(
        "/api/reports/review/text",
        json={"text": f"Procedimento com código TUSS {test_tuss_term.code} aprovado"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["inconsistencies"] == []


@pytest.mark.asyncio
async def test_review_texto_com_codigo_tuss_invalido_deve_apontar_inconsistencia(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/reports/review/text",
        json={"text": "Código 99999999 não existe na tabela"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    incons = resp.json()["inconsistencies"]
    assert len(incons) >= 1
    assert any("99999999" in i["message"] for i in incons)


@pytest.mark.asyncio
async def test_review_texto_vazio_deve_apontar_inconsistencia_de_conteudo(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/reports/review/text",
        json={"text": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    incons = resp.json()["inconsistencies"]
    assert any(i["field"] == "conteudo" for i in incons)
