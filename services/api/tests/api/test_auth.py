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
        json={"email": "novo@medreport.com", "password": "Senha123"},
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
        json={"email": test_user.email, "password": "OutraSenha1"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_registro_sem_email_deve_retornar_422(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={"password": "Senha123"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_registro_senha_fraca_deve_retornar_422(client: AsyncClient):
    """Senha sem maiúscula, sem dígito ou menor que 8 chars deve ser rejeitada pelo backend."""
    casos = [
        "semaiuscula1",      # sem maiúscula
        "SEMNUMERO",        # sem número e sem minúscula
        "Curta1",           # < 8 chars
        "semdigito",        # sem dígito e sem maiúscula
    ]
    for senha in casos:
        resp = await client.post(
            "/api/auth/register",
            json={"email": f"teste_{senha}@x.com", "password": senha},
        )
        assert resp.status_code == 422, f"Esperava 422 para senha '{senha}', got {resp.status_code}"


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
    assert "Credenciais" in resp.json()["detail"]


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


# ─── CRM/nome no registro ───

@pytest.mark.asyncio
async def test_registro_com_nome_crm_deve_retornar_dados_completos(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "dr.crm@medreport.com",
            "password": "Senha123",
            "nome": "Dr. Ana Lima",
            "crm": "654321",
            "crm_uf": "RJ",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["nome"] == "Dr. Ana Lima"
    assert body["user"]["crm"] == "654321"
    assert body["user"]["crm_uf"] == "RJ"


@pytest.mark.asyncio
async def test_registro_com_crm_invalido_deve_retornar_422(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "dr.invalido@medreport.com",
            "password": "Senha123",
            "nome": "Dr. X",
            "crm": "abc123",
            "crm_uf": "SP",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_registro_com_uf_invalida_deve_retornar_422(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "dr.uf@medreport.com",
            "password": "Senha123",
            "nome": "Dr. Y",
            "crm": "123456",
            "crm_uf": "XX",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_me_deve_retornar_nome_e_crm(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    resp = await client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "nome" in body
    assert "crm" in body
    assert "crm_uf" in body


@pytest.mark.asyncio
async def test_patch_me_deve_atualizar_nome_e_crm(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.patch(
        "/api/auth/me",
        json={"nome": "Dr. Novo Nome", "crm": "999999", "crm_uf": "MG"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nome"] == "Dr. Novo Nome"
    assert body["crm"] == "999999"
    assert body["crm_uf"] == "MG"


@pytest.mark.asyncio
async def test_patch_me_nao_deve_alterar_role_ou_email(
    client: AsyncClient, auth_headers: dict, test_user: User
):
    resp = await client.patch(
        "/api/auth/me",
        json={"nome": "Dr. X", "crm": "111111", "crm_uf": "SP", "role": "admin", "email": "hacker@x.com"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == test_user.email
    assert body["role"] == "medico"


@pytest.mark.asyncio
async def test_patch_me_sem_auth_deve_retornar_401(client: AsyncClient):
    resp = await client.patch("/api/auth/me", json={"nome": "Dr. X"})
    assert resp.status_code == 401
