# Design Spec: Login com CRM/Nome + Assinatura Eletrônica

**Data:** 2026-03-22
**Status:** Aprovado
**Projeto:** MedReport

---

## Visão Geral

Duas features complementares:

1. **Coleta de nome e CRM no cadastro** — para que o nome e CRM do médico apareçam automaticamente nos relatórios gerados.
2. **Assinatura eletrônica simples com hash SHA-256** — botão "Assinar" no relatório que registra timestamp, dados do médico e um fingerprint SHA-256 do documento como evidência de integridade do conteúdo.

> **Nota legal:** A assinatura SHA-256 implementada aqui é uma assinatura eletrônica simples (registro de autoria + integridade de conteúdo). Não possui validade jurídica equivalente a certificado ICP-Brasil (MP 2.200-2/2001). O sistema deve comunicar isso claramente ao usuário na interface.

---

## Feature 1: Nome e CRM no Cadastro

### Modelo de Dados — `users`

Três novos campos na tabela `users`:

| Campo | Tipo | Constraints |
|-------|------|-------------|
| `nome` | `String(255)` | nullable=True (existentes ficam null) |
| `crm` | `String(50)` | nullable=True |
| `crm_uf` | `String(2)` | nullable=True |

> Campos nullable para não quebrar usuários existentes. Novos registros os exigem via validação da API.
> Não há constraint de unicidade em `(crm, crm_uf)` — o mesmo número pode existir em UFs diferentes (são médicos distintos).

### Validações — servidor

- `crm`: apenas dígitos, 4–8 caracteres (validado via regex `^\d{4,8}$`)
- `crm_uf`: deve ser uma das 27 siglas de estado válidas
- `nome`: não vazio, máximo 255 caracteres
- `PATCH /auth/me`: permite atualizar apenas `nome`, `crm`, `crm_uf` — campos `role`, `email`, `id` são ignorados mesmo se enviados

### API

**`POST /auth/register`** — campos adicionais obrigatórios para novos registros:
```json
{
  "email": "dr@exemplo.com",
  "password": "senha123",
  "nome": "Dr. João Silva",
  "crm": "123456",
  "crm_uf": "SP"
}
```

Respostas de erro:
- `409` — e-mail já cadastrado
- `422` — campos inválidos (crm com letras, crm_uf inválida, etc.)

**`GET /auth/me`** — `UserOut` passa a incluir:
```json
{
  "id": "...",
  "email": "...",
  "role": "medico",
  "nome": "Dr. João Silva",
  "crm": "123456",
  "crm_uf": "SP",
  "legal_basis_acknowledged": true
}
```

**`PATCH /auth/me`** — atualiza nome/CRM após cadastro (campos independentes, todos opcionais):
```json
{ "nome": "Dr. João Silva", "crm": "123456", "crm_uf": "SP" }
```

Respostas de erro:
- `401` — não autenticado
- `422` — formato inválido de crm ou crm_uf

### Frontend — `Register.tsx`

Campos adicionados ao formulário (antes do email):
- **Nome completo** — `<Input type="text">`, obrigatório
- **CRM** — `<Input type="text" inputMode="numeric">`, obrigatório, validação só números
- **UF do CRM** — `<Select>` com os 27 estados brasileiros, obrigatório

Visual: mantém o mesmo estilo minimalista profissional da tela atual (fundo `#f8fafc`, card branco com sombra leve, tipografia Chakra UI). O formulário ficará mais longo — considerar scroll interno no card.

### Fluxo

```
Register → salva nome/crm/crm_uf → login automático → /legal-basis → /dashboard
```

O `localStorage` salva o objeto `user` completo incluindo nome e CRM. No logout, `localStorage` é limpo completamente.

---

## Feature 2: Assinatura Eletrônica com Hash SHA-256

### Modelo de Dados — `reports`

Quatro campos novos na tabela `reports` (`signed_at` já existe e será preenchido):

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `medico_nome` | `String(255)` | Snapshot do nome no momento da assinatura |
| `medico_crm` | `String(50)` | Snapshot do CRM |
| `medico_crm_uf` | `String(2)` | Snapshot da UF |
| `signature_hash` | `String(64)` | SHA-256 hex dos bytes do DOCX gerado |

> Os campos são snapshot imutáveis — mesmo que o médico atualize o perfil depois, a assinatura preserva os dados originais do momento da assinatura.

### Máquina de Estados — `status` do relatório

```
draft → generating → review → approved → signed
                   ↑__________________________↑
                   (ambos permitem assinar)
```

O botão "Assinar" é visível quando `status ∈ {"review", "approved"}`.
Um relatório `signed` não pode ser re-assinado (retorna `409`).

### Pré-condição para assinar

Se o usuário autenticado tiver `crm == null` (conta criada antes desta feature), o endpoint `/sign` retorna `422` com mensagem clara: *"Complete seu perfil com CRM antes de assinar."* O frontend deve redirecionar para a página de perfil.

### API — `POST /reports/{id}/sign`

**Fluxo interno (transacional):**
1. Verifica autenticação → `401` se não autenticado
2. Busca relatório → `404` se não encontrado
3. Verifica propriedade (`report.user_id == current_user_id`) → `403` se não for dono
4. Verifica status (`signed`) → `409 Already signed` se já assinado
5. Verifica que `user.crm` não é null → `422` se null
6. Gera DOCX em memória com nome/CRM preenchidos
7. Se geração falhar → `500`, nenhuma escrita no banco
8. Calcula SHA-256 dos bytes do DOCX
9. Em uma única transação: persiste `signed_at`, `medico_nome`, `medico_crm`, `medico_crm_uf`, `signature_hash`, `status="signed"`
10. Retorna `200`:

```json
{
  "signed_at": "2026-03-22T14:30:00Z",
  "signature_hash": "a3f2c1d4e5f6...",
  "medico_nome": "Dr. João Silva",
  "medico_crm": "123456",
  "medico_crm_uf": "SP"
}
```

**`GET /reports/{id}/download`**
- `status == "signed"` → usa `medico_nome`, `medico_crm`, `medico_crm_uf` do banco (snapshot)
- `status != "signed"` → passa strings vazias (comportamento atual)

### Frontend — Botão de Assinatura

**Localização:** `ReportReview.tsx`

**Comportamento:**
- Visível quando `status ∈ {"review", "approved"}`
- Click abre **modal de confirmação** com:
  - Nome e CRM do médico (readonly, vindo do perfil)
  - Aviso: *"Esta assinatura eletrônica simples registra sua autoria e garante a integridade do documento via hash SHA-256. Não possui validade de certificado digital ICP-Brasil."*
  - Botão "Confirmar Assinatura" (colorScheme brand, com ícone de cadeado)
- Após assinar com sucesso:
  - Status atualizado para `signed`
  - Botão "Assinar" substituído por **"Baixar Relatório Assinado"** (colorScheme green)
  - Badge com hash resumido: `SHA-256: a3f2c1d4...` (primeiros 16 chars)

**Design:** Modal profissional com ícone shield/cadeado, tipografia clara, feedback de loading durante operação, sem elementos visuais que sugiram validade jurídica superior à real.

---

## Migração de Banco (Alembic)

`op.add_column` para:
- `users`: `nome`, `crm`, `crm_uf` — todos nullable
- `reports`: `medico_nome`, `medico_crm`, `medico_crm_uf`, `signature_hash` — todos nullable

`signed_at` já existe em `reports` — não precisa ser adicionado.

---

## Requisitos Não-Funcionais

- **Validação dupla (cliente + servidor):** CRM e UF validados em ambos os lados
- **Atomicidade:** Escrita da assinatura é transação única — ou tudo salva ou nada salva
- **Imutabilidade da assinatura:** Uma vez `signed`, campos `medico_*` e `signature_hash` não são atualizáveis por nenhum endpoint
- **Segurança do PATCH:** `/auth/me` aceita apenas `nome`, `crm`, `crm_uf` — outros campos são ignorados
- **Logout limpa localStorage:** Token e objeto `user` removidos no logout
- **Design profissional:** Todos os novos componentes seguem o padrão visual existente (Chakra UI, paleta brand, tipografia limpa, sem exageros visuais)

---

## Arquivos Afetados

| Arquivo | Mudança |
|---------|---------|
| `services/api/app/db/models.py` | +3 campos em `User`, +4 campos em `Report` |
| `services/api/app/api/auth.py` | `RegisterIn`, `UserOut`, validações, endpoint `PATCH /me` |
| `services/api/app/api/reports.py` | Endpoint `POST /{id}/sign`, atualizar download |
| `apps/web/src/api/auth.ts` | `User` type, `register()`, `updateProfile()` |
| `apps/web/src/pages/Register.tsx` | +3 campos no formulário |
| `apps/web/src/pages/ReportReview.tsx` | Modal de assinatura + botão |
| `alembic/versions/xxx_add_crm_and_signature.py` | Migration nova |
