# Login CRM/Nome + Assinatura Eletrônica — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar campos nome/CRM ao cadastro de médicos e implementar assinatura eletrônica simples com hash SHA-256 nos relatórios.

**Architecture:** Backend FastAPI com SQLAlchemy — novos campos adicionados via `ALTER TABLE` no `init_db.py` (padrão do projeto, sem Alembic — o spec menciona Alembic mas o projeto não usa; usamos `init_db.py`). Frontend React/Chakra UI — formulário de cadastro expandido e modal de assinatura no `ReportReview`.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, SQLite (testes), React/TypeScript, Chakra UI, hashlib (SHA-256)

---

## Chunk 1: Backend — Modelo, Auth API e Sign Endpoint

### Task 1: Adicionar campos ao modelo User e init_db

**Files:**
- Modify: `services/api/app/db/models.py`
- Modify: `services/api/app/db/init_db.py`

- [ ] **Step 1: Adicionar campos ao modelo User em models.py**

Localizar a classe `User` (após `consent_at`) e adicionar:

```python
# Dados profissionais do médico
nome = Column(String(255), nullable=True)
crm = Column(String(50), nullable=True)
crm_uf = Column(String(2), nullable=True)
```

- [ ] **Step 2: Adicionar campos ao modelo Report em models.py**

Localizar a classe `Report` e adicionar os campos ANTES de `created_at` (que é a última coluna) — inserir após `signed_at`:

```python
# Snapshot dos dados do médico no momento da assinatura
medico_nome = Column(String(255), nullable=True)
medico_crm = Column(String(50), nullable=True)
medico_crm_uf = Column(String(2), nullable=True)
signature_hash = Column(String(64), nullable=True)
```

- [ ] **Step 3: Registrar novas colunas no init_db.py**

**ATENÇÃO:** A lista `REPORT_NEW_COLUMNS` já existe com 6 entradas (`rol_version_id`, `dut_version_id`, etc.). Não substitua — **appende** as 4 novas entradas no final da lista existente:

```python
# Adicionar ao final da lista REPORT_NEW_COLUMNS já existente:
    ("medico_nome", "VARCHAR(255)"),
    ("medico_crm", "VARCHAR(50)"),
    ("medico_crm_uf", "VARCHAR(2)"),
    ("signature_hash", "VARCHAR(64)"),
```

Adicionar nova lista para `users` após `REPORT_NEW_COLUMNS`:

```python
USER_NEW_COLUMNS = [
    ("nome", "VARCHAR(255)"),
    ("crm", "VARCHAR(50)"),
    ("crm_uf", "VARCHAR(2)"),
]
```

- [ ] **Step 4: Executar ALTER TABLE para users no init_db.py**

Na função `create_tables()`, após o bloco de `clinical_evidences`, adicionar:

```python
async with engine.begin() as conn:
    for col_name, col_type in USER_NEW_COLUMNS:
        try:
            await conn.execute(text(
                f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"
            ))
            logger.info("Added column users.%s", col_name)
        except Exception:
            pass
```

- [ ] **Step 5: Commit**

```bash
git add services/api/app/db/models.py services/api/app/db/init_db.py
git commit -m "feat: add nome/crm fields to User and medico snapshot fields to Report"
```

---

### Task 2: Atualizar Auth API (register, me, PATCH /me)

**Files:**
- Modify: `services/api/app/api/auth.py`

- [ ] **Step 1: Escrever testes de falha primeiro**

Abrir `services/api/tests/api/test_auth.py` e adicionar ao final:

```python
# ─── CRM/nome no registro ───

@pytest.mark.asyncio
async def test_registro_com_nome_crm_deve_retornar_dados_completos(client: AsyncClient):
    resp = await client.post(
        "/api/auth/register",
        json={
            "email": "dr.crm@medreport.com",
            "password": "senha123",
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
            "password": "senha123",
            "nome": "Dr. X",
            "crm": "abc123",  # letras não permitidas
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
            "password": "senha123",
            "nome": "Dr. Y",
            "crm": "123456",
            "crm_uf": "XX",  # UF inexistente
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
```

- [ ] **Step 2: Executar testes para confirmar que falham**

```bash
cd services/api
pytest tests/api/test_auth.py -k "crm or patch_me or nome" -v
```

Esperado: todos FAIL (campos e endpoint não existem ainda)

- [ ] **Step 3: Atualizar UserOut para incluir novos campos**

Em `auth.py`, atualizar `UserOut`:

```python
class UserOut(BaseModel):
    id: str
    email: str
    role: str
    nome: str | None = None
    crm: str | None = None
    crm_uf: str | None = None
    legal_basis_acknowledged: bool

    class Config:
        from_attributes = True
```

- [ ] **Step 4: Definir constantes de validação e atualizar RegisterIn**

Adicionar após os imports em `auth.py`:

```python
import re

VALID_UFS = {
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO",
    "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI",
    "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
}
CRM_REGEX = re.compile(r"^\d{4,8}$")
```

Atualizar `RegisterIn`:

```python
class RegisterIn(BaseModel):
    email: str
    password: str
    role: str = "medico"
    nome: str | None = None
    crm: str | None = None
    crm_uf: str | None = None
```

- [ ] **Step 5: Adicionar validação no endpoint register**

No endpoint `register`, após a validação de role, adicionar:

```python
# Valida nome (não vazio)
if body.nome is not None and not body.nome.strip():
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Nome não pode ser vazio.",
    )
# Valida CRM e UF se fornecidos
if body.crm and not CRM_REGEX.match(body.crm):
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="CRM inválido. Use apenas dígitos (4-8 caracteres).",
    )
if body.crm_uf and body.crm_uf.upper() not in VALID_UFS:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"UF inválida: {body.crm_uf}",
    )
```

Atualizar a criação do `User` para incluir os novos campos:

```python
user = User(
    email=body.email,
    hashed_password=get_password_hash(body.password),
    role=body.role,
    nome=body.nome,
    crm=body.crm,
    crm_uf=body.crm_uf.upper() if body.crm_uf else None,
)
```

Atualizar o `UserOut` retornado no register para incluir os campos:

```python
return {
    "access_token": access_token,
    "token_type": "bearer",
    "user": UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role.value if hasattr(user.role, 'value') else user.role,
        nome=user.nome,
        crm=user.crm,
        crm_uf=user.crm_uf,
        legal_basis_acknowledged=False,
    ),
}
```

- [ ] **Step 6: Atualizar endpoint /me (GET) para retornar nome/crm**

No endpoint `me`, atualizar o return:

```python
return UserOut(
    id=str(user.id),
    email=user.email,
    role=user.role.value,
    nome=user.nome,
    crm=user.crm,
    crm_uf=user.crm_uf,
    legal_basis_acknowledged=user.legal_basis_acknowledged or False,
)
```

- [ ] **Step 7: Atualizar endpoint /token (login) para retornar nome/crm**

No endpoint `login`, atualizar o return:

```python
return {
    "access_token": access_token,
    "token_type": "bearer",
    "user": UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role.value,
        nome=user.nome,
        crm=user.crm,
        crm_uf=user.crm_uf,
        legal_basis_acknowledged=user.legal_basis_acknowledged or False,
    ),
}
```

- [ ] **Step 8: Adicionar endpoint PATCH /auth/me**

Adicionar após o endpoint `me`:

```python
class UpdateProfileIn(BaseModel):
    nome: str | None = None
    crm: str | None = None
    crm_uf: str | None = None


@router.patch("/me")
async def update_me(
    body: UpdateProfileIn,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if body.crm and not CRM_REGEX.match(body.crm):
        raise HTTPException(status_code=422, detail="CRM inválido. Use apenas dígitos (4-8 caracteres).")
    if body.crm_uf and body.crm_uf.upper() not in VALID_UFS:
        raise HTTPException(status_code=422, detail=f"UF inválida: {body.crm_uf}")

    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.nome is not None:
        user.nome = body.nome
    if body.crm is not None:
        user.crm = body.crm
    if body.crm_uf is not None:
        user.crm_uf = body.crm_uf.upper()

    await db.commit()
    await db.refresh(user)
    return UserOut(
        id=str(user.id),
        email=user.email,
        role=user.role.value,
        nome=user.nome,
        crm=user.crm,
        crm_uf=user.crm_uf,
        legal_basis_acknowledged=user.legal_basis_acknowledged or False,
    )
```

- [ ] **Step 9: Executar testes para confirmar que passam**

```bash
cd services/api
pytest tests/api/test_auth.py -v
```

Esperado: todos PASS (incluindo os testes novos)

- [ ] **Step 10: Commit**

```bash
git add services/api/app/api/auth.py services/api/tests/api/test_auth.py
git commit -m "feat: add nome/crm to auth register, me and PATCH /me endpoints"
```

---

### Task 3: Endpoint de Assinatura POST /reports/{id}/sign

**Files:**
- Modify: `services/api/app/api/reports.py`
- Modify: `services/api/tests/api/test_reports.py`

- [ ] **Step 1: Escrever testes de falha primeiro**

Adicionar ao final de `services/api/tests/api/test_reports.py`. **Primeiro adicione os imports** que não existem no arquivo (verifique o topo do arquivo — `get_password_hash` e `create_access_token` NÃO estão importados atualmente):

```python
from app.core.security import get_password_hash, create_access_token
```

Depois adicionar as fixtures e testes:

```python
# ─── POST /api/reports/{id}/sign ───

@pytest_asyncio.fixture
async def test_user_with_crm(db: AsyncSession) -> User:
    """Usuário médico com CRM preenchido para testes de assinatura."""
    from tests.api.conftest import TEST_PASSWORD
    user = User(
        id=uuid.uuid4(),
        email="dr.assinador@medreport.com",
        hashed_password=get_password_hash(TEST_PASSWORD),
        role="medico",
        nome="Dr. Carlos Assinador",
        crm="123456",
        crm_uf="SP",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers_crm(test_user_with_crm: User) -> dict:
    token = create_access_token(data={"sub": str(test_user_with_crm.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def report_in_review(client: AsyncClient, auth_headers_crm: dict) -> dict:
    """Cria um relatório e força status para review."""
    resp = await client.post("/api/reports", json=REPORT_PAYLOAD, headers=auth_headers_crm)
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_assinar_relatorio_deve_retornar_hash(
    client: AsyncClient, auth_headers_crm: dict, report_in_review: dict
):
    report_id = report_in_review["id"]
    resp = await client.post(f"/api/reports/{report_id}/sign", headers=auth_headers_crm)
    assert resp.status_code == 200
    body = resp.json()
    assert "signature_hash" in body
    assert len(body["signature_hash"]) == 64  # SHA-256 hex
    assert "signed_at" in body
    assert body["medico_nome"] == "Dr. Carlos Assinador"
    assert body["medico_crm"] == "123456"
    assert body["medico_crm_uf"] == "SP"


@pytest.mark.asyncio
async def test_assinar_relatorio_ja_assinado_deve_retornar_409(
    client: AsyncClient, auth_headers_crm: dict, report_in_review: dict
):
    report_id = report_in_review["id"]
    await client.post(f"/api/reports/{report_id}/sign", headers=auth_headers_crm)
    resp = await client.post(f"/api/reports/{report_id}/sign", headers=auth_headers_crm)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_assinar_relatorio_de_outro_usuario_deve_retornar_403(
    client: AsyncClient, auth_headers: dict, report_in_review: dict
):
    """auth_headers pertence ao test_user (sem CRM), não ao dono do relatório."""
    report_id = report_in_review["id"]
    resp = await client.post(f"/api/reports/{report_id}/sign", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_assinar_relatorio_sem_crm_deve_retornar_422(
    client: AsyncClient, auth_headers: dict, db: AsyncSession
):
    """Usuário sem CRM não pode assinar."""
    # Cria relatório com usuário sem CRM
    resp_create = await client.post("/api/reports", json=REPORT_PAYLOAD, headers=auth_headers)
    report_id = resp_create.json()["id"]
    resp = await client.post(f"/api/reports/{report_id}/sign", headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_assinar_relatorio_inexistente_deve_retornar_404(
    client: AsyncClient, auth_headers_crm: dict
):
    resp = await client.post(
        f"/api/reports/{uuid.uuid4()}/sign", headers=auth_headers_crm
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_assinar_sem_auth_deve_retornar_401(client: AsyncClient, report_in_review: dict):
    resp = await client.post(f"/api/reports/{report_in_review['id']}/sign")
    assert resp.status_code == 401
```

- [ ] **Step 2: Executar testes para confirmar que falham**

```bash
cd services/api
pytest tests/api/test_reports.py -k "assinar" -v
```

Esperado: todos FAIL (endpoint não existe)

- [ ] **Step 3: Implementar endpoint POST /reports/{id}/sign**

Adicionar os imports necessários no topo de `reports.py`:

```python
import hashlib
from datetime import datetime
```

**ATENÇÃO:** O arquivo `reports.py` já possui um stub `@router.post("/{report_id}/sign")`. **Substitua** esse stub existente pela implementação completa abaixo — não adicione uma nova rota duplicada.

```python
@router.post("/{report_id}/sign")
async def sign_report(
    report_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Assina eletronicamente o relatório gerando hash SHA-256 do DOCX."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Busca relatório
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")

    # Verifica propriedade
    if str(report.user_id) != user_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    # Verifica se já assinado
    if report.status == "signed":
        raise HTTPException(status_code=409, detail="Relatório já assinado")

    # Busca dados do médico
    user_result = await db.execute(select(User).where(User.id == UUID(str(user_id))))
    user = user_result.scalar_one_or_none()
    if not user or not user.crm:
        raise HTTPException(
            status_code=422,
            detail="Complete seu perfil com CRM antes de assinar.",
        )

    # Gera DOCX em memória com dados do médico
    from app.services.docx_generator import generate_docx_bytes
    try:
        docx_bytes = generate_docx_bytes(
            justificativa=report.justificativa_ia or "",
            paciente_nome=report.paciente_nome or "",
            cid=report.cid or "",
            diagnostico_resumo=report.diagnosis or "",
            produto_nome=report.materials or "",
            convenio=report.health_plan or "",
            especialidade=getattr(report, "especialidade", "") or "",
            codigo_tuss="",
            referencias=[],
            checklist=None,
            aprovado=False,
            falha_terapeutica=getattr(report, "falha_terapeutica", "") or "",
            risco_nao_realizacao=getattr(report, "risco_nao_realizacao", "") or "",
            base_legal=getattr(report, "base_legal_ans", "") or "",
            medico_nome=user.nome or "",
            medico_crm=f"CRM/{user.crm_uf} {user.crm}" if user.crm_uf else user.crm,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar documento: {str(e)}")

    # Calcula SHA-256
    signature_hash = hashlib.sha256(docx_bytes).hexdigest()
    signed_at = datetime.utcnow()

    # Persiste em transação única
    report.signed_at = signed_at
    report.status = "signed"
    report.medico_nome = user.nome
    report.medico_crm = user.crm
    report.medico_crm_uf = user.crm_uf
    report.signature_hash = signature_hash
    await db.commit()

    return {
        "signed_at": signed_at.isoformat() + "Z",
        "signature_hash": signature_hash,
        "medico_nome": user.nome,
        "medico_crm": user.crm,
        "medico_crm_uf": user.crm_uf,
    }
```

- [ ] **Step 4: Atualizar endpoint de download para usar snapshot do médico**

No endpoint de download, localizar o bloco `common_kwargs = dict(...)` e adicionar ao dicionário:

```python
medico_nome=getattr(r, "medico_nome", "") or "",
medico_crm=(
    f"CRM/{r.medico_crm_uf} {r.medico_crm}"
    if getattr(r, "medico_crm", None) and getattr(r, "medico_crm_uf", None)
    else (getattr(r, "medico_crm", "") or "")
),
```

- [ ] **Step 5: Executar testes para confirmar que passam**

```bash
cd services/api
pytest tests/api/test_reports.py -v
```

Esperado: todos PASS

- [ ] **Step 6: Commit**

```bash
git add services/api/app/api/reports.py services/api/tests/api/test_reports.py
git commit -m "feat: add POST /reports/{id}/sign with SHA-256 hash and snapshot"
```

---

## Chunk 2: Frontend — Register, Auth Types e Modal de Assinatura

### Task 4: Atualizar tipos e API do frontend

**Files:**
- Modify: `apps/web/src/api/auth.ts`

- [ ] **Step 1: Atualizar o type User para incluir novos campos**

Em `auth.ts`, atualizar o type `User`:

```typescript
export type User = {
  id: string;
  email: string;
  role: 'medico' | 'distribuidor' | 'admin';
  nome?: string;
  crm?: string;
  crm_uf?: string;
  legal_basis_acknowledged: boolean;
};
```

- [ ] **Step 2: Atualizar a assinatura do método register**

Em `auth.ts`, atualizar o método `register`:

```typescript
register(email: string, password: string, nome: string, crm: string, crm_uf: string) {
  return apiRequest<LoginResponse>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, nome, crm, crm_uf }),
  });
},
```

- [ ] **Step 3: Adicionar método updateProfile**

Após o método `register`, adicionar:

```typescript
updateProfile(data: { nome?: string; crm?: string; crm_uf?: string }) {
  return apiRequest<User>('/auth/me', {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
},
```

- [ ] **Step 4: Atualizar tipo SignResponse na api de reports**

Em `apps/web/src/api/reports.ts`, atualizar o método `sign`:

```typescript
sign(id: string) {
  return apiRequest<{
    signed_at: string;
    signature_hash: string;
    medico_nome: string;
    medico_crm: string;
    medico_crm_uf: string;
  }>(`/reports/${id}/sign`, { method: 'POST' });
},
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/api/auth.ts apps/web/src/api/reports.ts
git commit -m "feat: update auth types and api for nome/crm and sign response"
```

---

### Task 5: Atualizar Register.tsx com campos nome/CRM

**Files:**
- Modify: `apps/web/src/pages/Register.tsx`

- [ ] **Step 1: Adicionar estados para novos campos**

Localizar os estados no início do componente e adicionar após `confirmPassword`:

```typescript
const [nome, setNome] = useState('');
const [crm, setCrm] = useState('');
const [crmUf, setCrmUf] = useState('');
```

- [ ] **Step 2: Adicionar validação de CRM no handleSubmit**

No `handleSubmit`, após a validação de senha, adicionar:

```typescript
if (!nome.trim()) {
  toast({ title: 'Nome completo é obrigatório', status: 'error' });
  return;
}
if (!/^\d{4,8}$/.test(crm)) {
  toast({ title: 'CRM inválido. Use apenas dígitos (4-8 caracteres)', status: 'error' });
  return;
}
if (!crmUf) {
  toast({ title: 'Selecione a UF do CRM', status: 'error' });
  return;
}
```

- [ ] **Step 3: Atualizar chamada ao authApi.register**

Substituir:
```typescript
const res = await authApi.register(email, password);
```
Por:
```typescript
const res = await authApi.register(email, password, nome, crm, crmUf);
```

- [ ] **Step 4: Adicionar imports do Select no topo**

Adicionar `Select` aos imports do Chakra UI existentes:

```typescript
import {
  Box, Button, FormControl, FormLabel, Input, VStack, Text,
  useToast, HStack, Link, Select,
} from '@chakra-ui/react';
```

- [ ] **Step 5: Adicionar constante com UFs brasileiras**

Antes do componente `Register`, adicionar:

```typescript
const UFS_BRASIL = [
  'AC','AL','AP','AM','BA','CE','DF','ES','GO',
  'MA','MT','MS','MG','PA','PB','PR','PE','PI',
  'RJ','RN','RS','RO','RR','SC','SP','SE','TO',
];
```

- [ ] **Step 6: Adicionar campos ao formulário**

No JSX, dentro do `<VStack gap={4} align="stretch">`, adicionar os campos ANTES do campo de e-mail:

```tsx
<FormControl isRequired>
  <FormLabel fontSize="sm" fontWeight="500" color="gray.700">
    Nome completo
  </FormLabel>
  <Input
    type="text"
    value={nome}
    onChange={(e) => setNome(e.target.value)}
    placeholder="Dr. João da Silva"
    size="lg"
    fontSize="sm"
    borderRadius="lg"
  />
</FormControl>

<HStack gap={3} align="flex-end">
  <FormControl isRequired flex={1}>
    <FormLabel fontSize="sm" fontWeight="500" color="gray.700">
      CRM
    </FormLabel>
    <Input
      type="text"
      inputMode="numeric"
      value={crm}
      onChange={(e) => setCrm(e.target.value.replace(/\D/g, '').slice(0, 8))}
      placeholder="123456"
      size="lg"
      fontSize="sm"
      borderRadius="lg"
    />
  </FormControl>
  <FormControl isRequired w="110px">
    <FormLabel fontSize="sm" fontWeight="500" color="gray.700">
      UF
    </FormLabel>
    <Select
      value={crmUf}
      onChange={(e) => setCrmUf(e.target.value)}
      size="lg"
      fontSize="sm"
      borderRadius="lg"
      placeholder="UF"
    >
      {UFS_BRASIL.map((uf) => (
        <option key={uf} value={uf}>{uf}</option>
      ))}
    </Select>
  </FormControl>
</HStack>
```

- [ ] **Step 7: Verificar visualmente no browser**

```bash
cd apps/web
npm run dev
```

Abrir `http://localhost:5173/register` e verificar:
- Campos Nome, CRM e UF aparecem antes do email
- Campo CRM aceita apenas dígitos
- Select de UF lista os 27 estados
- Formulário mantém estilo profissional (fundo branco, bordas sutis)

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/pages/Register.tsx
git commit -m "feat: add nome, CRM and UF fields to Register form"
```

---

### Task 6: Modal de Assinatura no ReportReview.tsx

**Files:**
- Modify: `apps/web/src/pages/ReportReview.tsx`

- [ ] **Step 1: Verificar estado atual do arquivo**

Ler `apps/web/src/pages/ReportReview.tsx` por completo para entender o que já existe (já tem `signing` state e `reportsApi.sign(id)` básico).

- [ ] **Step 2: Adicionar imports necessários**

Localizar os imports do Chakra UI e adicionar:

```typescript
import {
  Box, Button, Text, VStack, HStack, Flex, useToast, Badge,
  SimpleGrid, Spinner, Icon,
  Modal, ModalOverlay, ModalContent, ModalHeader, ModalBody,
  ModalFooter, ModalCloseButton, useDisclosure,
  Divider, Code,
} from '@chakra-ui/react';
import { FiArrowLeft, FiDownload, FiFileText, FiEdit3, FiShield, FiCheckCircle } from 'react-icons/fi';
```

- [ ] **Step 3: Adicionar estado para o resultado da assinatura e tipo**

Adicionar junto aos estados existentes:

```typescript
const { isOpen, onOpen, onClose } = useDisclosure();
const [signResult, setSignResult] = useState<{
  signed_at: string;
  signature_hash: string;
  medico_nome: string;
  medico_crm: string;
  medico_crm_uf: string;
} | null>(null);
const user = JSON.parse(localStorage.getItem('user') || '{}');
```

- [ ] **Step 4: Atualizar função handleSign**

Substituir a função `handleSign` existente por:

```typescript
const handleSign = async () => {
  if (!id) return;
  setSigning(true);
  try {
    const result = await reportsApi.sign(id);
    setSignResult(result);
    setReport((p) => (p ? { ...p, status: 'signed' } : null));
    onClose();
    toast({
      title: 'Relatório assinado com sucesso',
      description: `Hash: ${result.signature_hash.slice(0, 16)}...`,
      status: 'success',
      duration: 5000,
    });
  } catch (err: unknown) {
    const status = (err as { status?: number })?.status;
    if (status === 422) {
      toast({
        title: 'Perfil incompleto',
        description: 'Complete seu CRM no perfil antes de assinar.',
        status: 'warning',
        duration: 5000,
      });
      onClose();
      navigate('/profile');
    } else {
      toast({ title: 'Erro ao assinar relatório', status: 'error' });
    }
  } finally {
    setSigning(false);
  }
};
```

- [ ] **Step 5: Adicionar Modal de confirmação**

Antes do `return` do componente (ou logo após o JSX principal), adicionar o modal:

```tsx
{/* Modal de Assinatura */}
<Modal isOpen={isOpen} onClose={onClose} isCentered size="md">
  <ModalOverlay bg="blackAlpha.300" backdropFilter="blur(4px)" />
  <ModalContent borderRadius="xl" mx={4}>
    <ModalHeader pb={2}>
      <HStack gap={3}>
        <Box
          w="36px" h="36px"
          borderRadius="lg"
          bg="brand.50"
          display="flex"
          alignItems="center"
          justifyContent="center"
        >
          <Icon as={FiShield} color="brand.600" boxSize={5} />
        </Box>
        <Text fontSize="lg" fontWeight="600" color="gray.800">
          Assinar Relatório
        </Text>
      </HStack>
    </ModalHeader>
    <ModalCloseButton />
    <ModalBody pb={4}>
      <VStack gap={4} align="stretch">
        <Box bg="gray.50" borderRadius="lg" p={4}>
          <Text fontSize="xs" color="gray.500" fontWeight="500" mb={1}>
            MÉDICO RESPONSÁVEL
          </Text>
          <Text fontSize="sm" fontWeight="600" color="gray.800">
            {user.nome || '—'}
          </Text>
          <Text fontSize="sm" color="gray.600">
            CRM/{user.crm_uf} {user.crm}
          </Text>
        </Box>
        <Box
          bg="amber.50"
          border="1px solid"
          borderColor="orange.200"
          borderRadius="lg"
          p={3}
        >
          <Text fontSize="xs" color="orange.700" lineHeight="tall">
            Esta assinatura eletrônica simples registra sua autoria e garante a
            integridade do documento via hash SHA-256.{' '}
            <strong>Não possui validade de certificado digital ICP-Brasil.</strong>
          </Text>
        </Box>
      </VStack>
    </ModalBody>
    <ModalFooter gap={3}>
      <Button variant="ghost" onClick={onClose} size="sm" color="gray.600">
        Cancelar
      </Button>
      <Button
        colorScheme="brand"
        onClick={handleSign}
        isLoading={signing}
        loadingText="Assinando..."
        size="sm"
        leftIcon={<Icon as={FiShield} />}
        borderRadius="lg"
      >
        Confirmar Assinatura
      </Button>
    </ModalFooter>
  </ModalContent>
</Modal>
```

- [ ] **Step 6: Atualizar botão de assinar e adicionar botão "Baixar Assinado"**

Localizar o botão existente que chama `handleSign` diretamente e substituir pelo bloco abaixo (que mostra "Assinar" OU "Baixar Assinado" dependendo do status):

```tsx
{['review', 'approved'].includes(report.status) ? (
  <Button
    colorScheme="brand"
    onClick={onOpen}
    leftIcon={<Icon as={FiShield} />}
    borderRadius="lg"
    transition={buttonTransition}
    _hover={buttonHover}
  >
    Assinar Relatório
  </Button>
) : report.status === 'signed' ? (
  <Button
    colorScheme="green"
    onClick={() => handleDownload('pdf')}
    leftIcon={<Icon as={FiCheckCircle} />}
    borderRadius="lg"
    transition={buttonTransition}
    _hover={buttonHover}
  >
    Baixar Relatório Assinado
  </Button>
) : null}
```

- [ ] **Step 7: Atualizar type ReportDetail para incluir signature_hash**

No topo do arquivo, atualizar o tipo local **antes** de adicionar o badge (o tipo precisa existir para evitar cast `as any`):

```typescript
type ReportDetail = {
  id: string;
  status: string;
  cid?: string;
  diagnosis?: string;
  surgery_description?: string;
  materials?: string;
  health_plan?: string;
  created_at: string;
  inconsistencies?: { field: string; message: string }[];
  signature_hash?: string;
  medico_nome?: string;
  medico_crm?: string;
  medico_crm_uf?: string;
};
```

- [ ] **Step 8: Adicionar badge de hash após assinar**

Após o badge de status do relatório, adicionar exibição do hash quando assinado:

```tsx
{report.status === 'signed' && (signResult?.signature_hash || report.signature_hash) && (
  <HStack
    gap={2}
    bg="green.50"
    border="1px solid"
    borderColor="green.200"
    borderRadius="lg"
    px={3}
    py={2}
    mt={2}
  >
    <Icon as={FiCheckCircle} color="green.500" boxSize={4} />
    <Box>
      <Text fontSize="xs" color="green.700" fontWeight="600">
        Assinatura eletrônica registrada
      </Text>
      <Text fontSize="xs" color="green.600" fontFamily="mono">
        SHA-256: {(signResult?.signature_hash || report.signature_hash || '').slice(0, 16)}...
      </Text>
    </Box>
  </HStack>
)}
```

- [ ] **Step 9: Verificar visualmente no browser**

Navegar até um relatório existente e verificar:
- Botão "Assinar Relatório" aparece apenas quando status é `review` ou `approved`
- Em status `draft` ou `generating`, nenhum dos dois botões aparece
- Click abre modal com nome/CRM readonly e aviso legal
- Após assinar: badge verde com hash SHA-256 truncado aparece
- Botão "Assinar" some, botão "Baixar Relatório Assinado" (verde) aparece

- [ ] **Step 10: Commit**

```bash
git add apps/web/src/pages/ReportReview.tsx
git commit -m "feat: add signature modal with SHA-256 badge to ReportReview"
```

---

## Verificação Final

- [ ] **Rodar todos os testes de backend**

```bash
cd services/api
pytest tests/api/ -v
```

Esperado: todos PASS

- [ ] **Verificar fluxo completo manualmente**

1. Acessar `/register` → preencher nome, CRM, UF, email, senha → criar conta
2. Verificar que `localStorage.user` contém `nome`, `crm`, `crm_uf`
3. Criar um relatório e gerar a justificativa
4. Na tela de review, clicar "Assinar Relatório"
5. Modal abre com dados do médico corretos
6. Confirmar → badge SHA-256 aparece
7. Baixar DOCX → verificar que rodapé tem nome e CRM do médico

- [ ] **Commit final**

```bash
git add -A
git commit -m "feat: complete CRM/nome registration and electronic signature feature"
```
