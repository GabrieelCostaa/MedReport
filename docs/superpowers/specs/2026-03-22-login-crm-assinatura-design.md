# Design Spec: Login com CRM/Nome + Assinatura Eletrônica

**Data:** 2026-03-22
**Status:** Aprovado
**Projeto:** MedReport

---

## Visão Geral

Duas features complementares:

1. **Coleta de nome e CRM no cadastro** — para que o nome e CRM do médico apareçam automaticamente nos relatórios gerados.
2. **Assinatura eletrônica simples com hash SHA-256** — botão "Assinar" no relatório que registra timestamp, dados do médico e um fingerprint SHA-256 do documento como evidência de integridade.

---

## Feature 1: Nome e CRM no Cadastro

### Modelo de Dados — `users`

Três novos campos na tabela `users`:

| Campo | Tipo | Constraints |
|-------|------|-------------|
| `nome` | `String(255)` | nullable=False (obrigatório no registro) |
| `crm` | `String(50)` | nullable=False |
| `crm_uf` | `String(2)` | nullable=False, ex: "SP" |

### API

**`POST /auth/register`** — campos adicionais obrigatórios:
```json
{
  "email": "dr@exemplo.com",
  "password": "senha123",
  "nome": "Dr. João Silva",
  "crm": "123456",
  "crm_uf": "SP"
}
```

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

**`PATCH /auth/me`** — endpoint novo para atualizar nome/CRM após cadastro:
```json
{ "nome": "...", "crm": "...", "crm_uf": "..." }
```

### Frontend — `Register.tsx`

Campos adicionados ao formulário (antes do email):
- **Nome completo** — `<Input type="text">`, obrigatório
- **CRM** — `<Input type="text" inputMode="numeric">`, obrigatório, validação só números
- **UF do CRM** — `<Select>` com os 27 estados brasileiros, obrigatório

Visual: mantém o mesmo estilo minimalista profissional da tela atual (fundo `#f8fafc`, card branco com sombra leve, tipografia Chakra UI).

### Fluxo

```
Register → salva nome/crm/crm_uf → login automático → /legal-basis → /dashboard
```

O `localStorage` já salva o objeto `user` completo — nome e CRM ficam disponíveis em toda a aplicação sem chamadas extras.

---

## Feature 2: Assinatura Eletrônica com Hash SHA-256

### Modelo de Dados — `reports`

Três novos campos na tabela `reports` (mais `signed_at` que já existe):

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `medico_nome` | `String(255)` | Snapshot do nome no momento da assinatura |
| `medico_crm` | `String(50)` | Snapshot do CRM |
| `medico_crm_uf` | `String(2)` | Snapshot da UF |
| `signature_hash` | `String(64)` | SHA-256 dos bytes do DOCX gerado |

> Os campos são snapshot — mesmo que o médico atualize o perfil depois, a assinatura preserva os dados originais.

### API — `POST /reports/{id}/sign`

**Fluxo interno:**
1. Verifica autenticação e propriedade do relatório
2. Busca dados do médico (`nome`, `crm`, `crm_uf`) do usuário autenticado
3. Gera o DOCX em memória com `medico_nome` e `medico_crm` preenchidos
4. Calcula `SHA-256` dos bytes do documento
5. Persiste no banco: `signed_at=now()`, `medico_nome`, `medico_crm`, `medico_crm_uf`, `signature_hash`
6. Atualiza `status` → `"signed"`
7. Retorna:
```json
{
  "signed_at": "2026-03-22T14:30:00Z",
  "signature_hash": "a3f2c1...",
  "medico_nome": "Dr. João Silva",
  "medico_crm": "123456",
  "crm_uf": "SP"
}
```

**`GET /reports/{id}/download`** — quando `status == "signed"`, passa `medico_nome`, `medico_crm`, `medico_crm_uf` para o `docx_generator`, que já possui os campos de rodapé implementados.

### Frontend — Botão de Assinatura

**Localização:** `ReportReview.tsx` (ou tela de visualização do relatório)

**Comportamento:**
- Visível quando `status == "review"` ou `"approved"`
- Abre **modal de confirmação** com:
  - Nome e CRM do médico (readonly, vindo do perfil — não editável aqui)
  - Aviso: *"Ao assinar, você confirma a veracidade das informações. Um hash SHA-256 será gerado como registro desta assinatura eletrônica."*
  - Botão "Confirmar Assinatura" (colorScheme brand)
- Após assinar com sucesso:
  - Status muda para `signed`
  - Botão "Assinar" é substituído por **"Baixar Relatório Assinado"**
  - Exibe hash resumido: `SHA-256: a3f2c1...` (primeiros 16 chars + "...")

**Design:** Modal profissional com ícone de cadeado/escudo, tipografia clara, feedback visual de loading durante a operação.

---

## Migração de Banco

Alembic migration com `op.add_column` para:
- `users`: `nome`, `crm`, `crm_uf`
- `reports`: `medico_nome`, `medico_crm`, `medico_crm_uf`, `signature_hash`

Usuários existentes terão `nome/crm = null` — sem quebra.

---

## Requisitos Não-Funcionais

- **Segurança:** Endpoint `/sign` verifica que o `user_id` do relatório corresponde ao usuário autenticado
- **Imutabilidade:** Uma vez assinado, o relatório não pode ser re-assinado (retorna 409)
- **Design:** Todo novo componente visual mantém o padrão profissional e elegante da aplicação existente (Chakra UI, paleta brand, tipografia limpa)
- **Backwards compatibility:** Campos novos nullable nos usuários existentes, sem migração de dados obrigatória

---

## Arquivos Afetados

| Arquivo | Mudança |
|---------|---------|
| `services/api/app/db/models.py` | +3 campos em `User`, +4 campos em `Report` |
| `services/api/app/api/auth.py` | `RegisterIn`, `UserOut`, endpoint `/me` PATCH |
| `services/api/app/api/reports.py` | Endpoint `/sign`, atualizar `/download` |
| `apps/web/src/api/auth.ts` | `User` type, `register()`, `updateProfile()` |
| `apps/web/src/pages/Register.tsx` | +3 campos no formulário |
| `apps/web/src/pages/ReportReview.tsx` | Modal de assinatura + botão |
| `alembic/versions/xxx_add_crm_and_signature.py` | Migration nova |
