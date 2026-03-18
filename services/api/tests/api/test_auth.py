"""
Testes de integração — Auth (login, /me, legal-basis).
Testa O QUE os endpoints fazem, não COMO fazem internamente.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User
from tests.api.conftest import TEST_PASSWORD


# ─── POST /api/auth/register ───


@pytest.mark.asyncio
async def test_registro_deve_criar_usuario_e_retornar_token(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"email": "novo@medreport.com", "password": "senha123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["email"] == "novo@medreport.com"
    assert body["user"]["role"] == "medico"

    # Token retornado deve funcionar
    me_resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {body['access_token']}"},
    )
    assert me_resp.status_code == 200


@pytest.mark.asyncio
async def test_registro_email_duplicado_deve_retornar_409(
    client: AsyncClient, test_user: User
):
    resp = await client.post(
        "/api/auth/register",
        json={"email": test_user.email, "password": "outra_senha"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_registro_sem_email_deve_retornar_422(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"password": "senha123"},
    )
    assert resp.status_code == 422


# ─── POST /auth/token ───


@pytest.mark.asyncio
async def test_login_deve_retornar_token_quando_credenciais_validas(
    client: AsyncClient, test_user: User
):
    resp = await client.post(
        "/auth/token",
        data={"username": test_user.email, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == test_user.email
    assert body["user"]["role"] == "medico"


@pytest.mark.asyncio
async def test_login_deve_retornar_401_quando_senha_errada(
    client: AsyncClient, test_user: User
):
    resp = await client.post(
        "/auth/token",
        data={"username": test_user.email, "password": "senha_errada"},
    )
    assert resp.status_code == 401
    assert "Incorrect" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_login_deve_retornar_401_quando_usuario_nao_existe(
    client: AsyncClient,
):
    resp = await client.post(
        "/auth/token",
        data={"username": "naoexiste@x.com", "password": "qualquer"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_deve_retornar_token_utilizavel_no_me(
    client: AsyncClient, test_user: User
):
    """Token retornado pelo login deve funcionar no endpoint /me."""
    login_resp = await client.post(
        "/auth/token",
        data={"username": test_user.email, "password": TEST_PASSWORD},
    )
    token = login_resp.json()["access_token"]

    me_resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == test_user.email


# ─── GET /api/auth/me ───


@pytest.mark.asyncio
async def test_me_deve_retornar_dados_do_usuario_autenticado(
    client: AsyncClient, test_user: User, auth_headers: dict
):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(test_user.id)
    assert body["email"] == test_user.email
    assert body["legal_basis_acknowledged"] is False


@pytest.mark.asyncio
async def test_me_deve_retornar_401_quando_token_invalido(
    client: AsyncClient,
):
    resp = await client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer token_invalido_xyz"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_sem_token_deve_retornar_401(client: AsyncClient):
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 401


# ─── POST /api/auth/legal-basis ───


@pytest.mark.asyncio
async def test_legal_basis_deve_registrar_ciencia_lgpd(
    client: AsyncClient, test_user: User, auth_headers: dict
):
    resp = await client.post("/api/auth/legal-basis", headers=auth_headers)
    assert resp.status_code == 200

    # Verifica que o estado foi persistido
    me_resp = await client.get("/api/auth/me", headers=auth_headers)
    assert me_resp.json()["legal_basis_acknowledged"] is True


@pytest.mark.asyncio
async def test_legal_basis_sem_auth_deve_retornar_401(client: AsyncClient):
    resp = await client.post("/api/auth/legal-basis")
    assert resp.status_code == 401
