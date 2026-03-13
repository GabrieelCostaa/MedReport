# Hugo — OPME Report Assistant: Guia Técnico do Desenvolvedor

> Documentação técnica completa do projeto para onboarding de novos desenvolvedores.
> Última atualização: Março 2026

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Infraestrutura e Setup Local](#3-infraestrutura-e-setup-local)
4. [Backend (FastAPI)](#4-backend-fastapi)
5. [Frontend (React)](#5-frontend-react)
6. [Pipeline Multi-Agente (Core do Produto)](#6-pipeline-multi-agente-core-do-produto)
7. [Compliance ANS](#7-compliance-ans)
8. [Banco de Dados](#8-banco-de-dados)
9. [Fluxo End-to-End: Geração de Relatório](#9-fluxo-end-to-end-geração-de-relatório)
10. [ETL de Dados Regulatórios](#10-etl-de-dados-regulatórios)
11. [Módulo de Cotações (RPA)](#11-módulo-de-cotações-rpa)
12. [Testes](#12-testes)
13. [Deploy e CI](#13-deploy-e-ci)

---

## 1. Visão Geral

### O que é

Hugo é um SaaS B2B2Médico que gera **relatórios técnicos de justificativa para materiais OPME** (Órteses, Próteses e Materiais Especiais). O objetivo é blindar o relatório contra glosas de convênios de saúde, usando IA para redigir textos tecnicamente robustos e legalmente fundamentados.

### Problema que resolve

Quando um médico solicita um material OPME a um convênio, o convênio pode **negar (glosar)** se a justificativa técnica for fraca. Hugo automatiza a geração de justificativas com:

- Evidências científicas (base interna + PubMed)
- Dados técnicos do produto (verdades absolutas)
- Fundamentação legal (RNs da ANS)
- Conformidade regulatória (TUSS, DUT, Anvisa)
- Auditoria automatizada contra alucinações

### Stack

| Camada | Tecnologia |
|--------|-----------|
| Frontend | React 18, Chakra UI, Vite, TypeScript |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2.0 (async) |
| Banco | PostgreSQL 16 |
| Cache | Redis 7 |
| Busca | Elasticsearch 8.11 |
| IA | OpenAI GPT-4o |
| PDF | WeasyPrint / ReportLab |
| Monorepo | npm workspaces + Turborepo |
| Infra local | Docker Compose |

---

## 2. Arquitetura

```
┌──────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                       │
│  Login → ReportCreate (4 steps) → ReportReview → PDF     │
│  Streaming via SSE (fetch + ReadableStream)               │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP/SSE (proxy :3000 → :8000)
┌────────────────────────▼─────────────────────────────────┐
│                   BACKEND (FastAPI)                        │
│                                                           │
│  ┌─────────┐  ┌──────────────────────────────────────┐   │
│  │  Auth   │  │     Pipeline Multi-Agente             │   │
│  │  CRUD   │  │                                       │   │
│  │  PDF    │  │  Researcher → Writer → Auditor → Val  │   │
│  │  TISS   │  │       ↕            ↕                  │   │
│  └─────────┘  │  Compliance Layer (DUT, TUSS, Anvisa) │   │
│               └──────────────────────────────────────┘   │
│                         │                                 │
│  ┌──────────────────────▼───────────────────────────┐    │
│  │  PostgreSQL  │  Redis  │  Elasticsearch  │ OpenAI │    │
│  └──────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────┘
```

### Estrutura de Diretórios

```
Hugo/
├── apps/
│   └── web/                          # Frontend React
│       ├── src/
│       │   ├── api/                  # Clientes HTTP (auth, ai, reports, products, etc.)
│       │   ├── components/           # Layout, ReportAssistant
│       │   ├── pages/                # Login, ReportCreate, ReportReview, etc.
│       │   ├── App.tsx               # Rotas
│       │   └── theme.ts              # Tema Chakra UI
│       ├── package.json
│       └── vite.config.ts            # Proxy /api → :8000
│
├── services/
│   └── api/                          # Backend Python
│       ├── app/
│       │   ├── api/                  # Rotas FastAPI
│       │   │   ├── auth.py           #   /auth, /api/auth
│       │   │   ├── ai.py             #   /api/ai (pipeline principal)
│       │   │   ├── reports.py        #   /api/reports (CRUD + PDF/XML)
│       │   │   ├── products.py       #   /api/products
│       │   │   ├── tuss.py           #   /api/tuss
│       │   │   ├── quotes.py         #   /api/quotes (RPA)
│       │   │   ├── erp_mock.py       #   /api/erp (mock)
│       │   │   └── notifications.py  #   /api/notifications (stub)
│       │   ├── core/
│       │   │   ├── config.py         # Settings (Pydantic)
│       │   │   └── security.py       # JWT, bcrypt
│       │   ├── db/
│       │   │   ├── models.py         # TODOS os modelos SQLAlchemy
│       │   │   ├── session.py        # Engine + SessionLocal
│       │   │   └── init_db.py        # create_tables() + seed()
│       │   ├── services/
│       │   │   ├── agents/           # ★ Pipeline multi-agente
│       │   │   │   ├── pipeline.py   #   Orquestrador
│       │   │   │   ├── researcher.py #   Agente A: Pesquisador
│       │   │   │   ├── writer.py     #   Agente B: Redator
│       │   │   │   ├── auditor.py    #   Agente C: Auditor
│       │   │   │   ├── validator.py  #   Camada 4: Validador hard-coded
│       │   │   │   ├── prompts.py    #   System prompts dos agentes
│       │   │   │   ├── checklist.py  #   Checklist de 6 itens
│       │   │   │   └── token_tracker.py
│       │   │   ├── compliance_layer.py  # Orquestrador de compliance ANS
│       │   │   ├── dut_engine.py        # Motor DUT-as-Code (DSL)
│       │   │   ├── tuss_validator.py    # Validador TUSS + TISS + Anvisa
│       │   │   ├── approval_score.py    # Score de completude documental
│       │   │   ├── pdf_generator.py     # Geração de PDF (WeasyPrint)
│       │   │   ├── tiss.py              # Geração de PDF/XML padrão TISS
│       │   │   ├── docx_generator.py    # Geração de DOCX
│       │   │   ├── pubmed_service.py    # Integração PubMed E-utilities
│       │   │   ├── tuss_search.py       # Busca TUSS
│       │   │   └── diff_engine.py       # Diff de edições
│       │   └── templates/
│       │       └── report_pdf.html      # Template Jinja2 para PDF
│       ├── scripts/
│       │   ├── etl/                     # ETL de dados regulatórios
│       │   │   ├── download_tuss.py     #   TUSS 19 do FTP ANS
│       │   │   ├── download_rol.py      #   Rol Anexo I (Excel)
│       │   │   ├── parse_dut_pdf.py     #   DUT Anexo II (PDF → LLM)
│       │   │   ├── check_anvisa.py      #   Status Anvisa
│       │   │   └── ingest_all.py        #   Orquestrador
│       │   ├── test_generate.py         # Teste em massa (10 cenários)
│       │   └── test_compliance_full.py  # Teste compliance ANS
│       ├── tests/                       # Testes unitários
│       ├── data/                        # Dados locais (estudos, relatórios aprovados)
│       ├── main.py                      # Entry point FastAPI
│       ├── requirements.txt
│       └── pytest.ini
│
├── docker-compose.yml                # PostgreSQL + Redis + Elasticsearch
├── package.json                      # Monorepo (npm workspaces)
├── turbo.json                        # Turborepo config
└── .github/workflows/ci.yml          # CI GitHub Actions
```

---

## 3. Infraestrutura e Setup Local

### Pré-requisitos

- Node.js >= 18
- Python 3.12
- Docker e Docker Compose

### Subir infraestrutura

```bash
docker compose up -d
# Sobe: PostgreSQL (:5432), Redis (:6379), Elasticsearch (:9200)
```

### Backend

```bash
cd services/api
pip install -r requirements.txt
# Copiar .env com DATABASE_URL, OPENAI_API_KEY, etc.
uvicorn main:app --reload --port 8000
# Na inicialização: cria tabelas + seed (user medico@opme.com / senha123)
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
# Sobe em http://localhost:3000, proxy automático para :8000
```

### Variáveis de Ambiente (`services/api/.env`)

| Variável | Obrigatória | Descrição |
|----------|:-----------:|-----------|
| `DATABASE_URL` | Sim | `postgresql+asyncpg://opme:opme_dev_secret@localhost:5432/opme` |
| `REDIS_URL` | Sim | `redis://localhost:6379/0` |
| `SECRET_KEY` | Sim | Chave JWT (qualquer string em dev) |
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI (GPT-4o) |
| `ELASTICSEARCH_URL` | Não | `http://localhost:9200` |
| `PUBMED_API_KEY` | Não | Chave PubMed para maior rate limit |
| `ANS_TUSS_FTP_URL` | Não | URL do ZIP TUSS no FTP ANS |
| `ANS_ROL_XLSX_URL` | Não | URL do Excel do Rol |
| `ANS_DUT_PDF_URL` | Não | URL do PDF da DUT |

---

## 4. Backend (FastAPI)

### Entry Point (`main.py`)

Na inicialização (`lifespan`):
1. `create_tables()` — cria todas as tabelas via `Base.metadata.create_all()` + `ALTER TABLE` para colunas novas
2. `seed()` — insere user padrão, 9 produtos OPME, templates por produto, evidências clínicas

CORS configurado para `localhost:3000`.

### Rotas API

| Router | Prefixo | Arquivo | Principais endpoints |
|--------|---------|---------|---------------------|
| Auth | `/auth`, `/api/auth` | `auth.py` | `POST /auth/token` (login), `GET /api/auth/me` |
| AI | `/api/ai` | `ai.py` | `POST /start-report-stream` (SSE), `POST /answer-stream`, `GET /download-pdf/{id}` |
| Reports | `/api/reports` | `reports.py` | CRUD, `POST /{id}/sign`, `GET /{id}/download?format=pdf\|xml` |
| Products | `/api/products` | `products.py` | `GET ?q=busca` (listagem com filtro) |
| TUSS | `/api/tuss` | `tuss.py` | `GET /search?q=` (busca terminologia) |
| Quotes | `/api/quotes` | `quotes.py` | Ingest RPA, listagem, budgets, webhooks |

### Autenticação

1. `POST /auth/token` — recebe `username` (email) + `password` como form-data (OAuth2)
2. Retorna JWT (HS256, expira em 7 dias)
3. Frontend armazena em `localStorage`
4. Todas as rotas protegidas usam `Depends(get_current_user_id)` que decodifica o Bearer token

### Geração de PDF

Existem **dois caminhos** para gerar PDF:

1. **`pdf_generator.py`** — Usa template Jinja2 (`report_pdf.html`) + WeasyPrint. Chamado pela rota `/api/ai/download-pdf/{id}`.
2. **`tiss.py`** — Gera PDF/XML no padrão TISS. Chamado pela rota `/api/reports/{id}/download`. Tem 3 fallbacks: WeasyPrint → ReportLab (Platypus) → ReportLab (Canvas).

---

## 5. Frontend (React)

### Rotas

| Rota | Página | Descrição |
|------|--------|-----------|
| `/login` | `Login.tsx` | Login com email/senha |
| `/legal-basis` | `LegalBasis.tsx` | Aceite LGPD (primeira vez) |
| `/reports` | `ReportList.tsx` | Lista de relatórios |
| `/reports/new` | `ReportCreate.tsx` | **Wizard de 4 etapas** (core do produto) |
| `/reports/:id/review` | `ReportReview.tsx` | Revisão, assinatura, download PDF/XML |
| `/quotes` | `QuotesDashboard.tsx` | Dashboard de cotações RPA |

### Clientes API (`src/api/`)

| Arquivo | Responsabilidade |
|---------|-----------------|
| `client.ts` | `apiRequest()` e `apiBlob()` base, injeta JWT |
| `auth.ts` | Login, me, acknowledgleLegalBasis |
| `ai-assistant.ts` | Pipeline SSE (`startReportStream`, `answerStream`), `quickCheck`, `saveEdit` |
| `reports.ts` | CRUD de reports, download PDF/XML, review |
| `products.ts` | Busca de produtos OPME |
| `evidences.ts` | Preview de evidências por CID |
| `quotes.ts` | Cotações |
| `tuss.ts` | Busca TUSS |

### SSE (Server-Sent Events)

O frontend **não usa `EventSource`**. Em vez disso, faz `fetch` com `ReadableStream` para ler chunks SSE manualmente. O formato é:

```
event: step
data: {"step":"researching","message":"Pesquisando evidências..."}

event: done
data: {"session_id":"...","justificativa":"...","checklist":{...}}
```

O componente `PipelineProgress` exibe as mensagens com efeito typewriter em tempo real.

### ReportCreate — As 4 Etapas

**Step 1: CID & Diagnóstico**
- Inputs: CID, especialidade, diagnóstico, procedimento cirúrgico
- Ao digitar CID, busca preview de evidências PubMed (debounce 500ms)
- Badge mostra: "X evidências internas + Y PubMed"

**Step 2: Paciente & Material**
- Inputs: nome do paciente, convênio
- Busca e seleção de produto OPME (cards)
- Botão "Gerar Justificativa com IA" inicia o pipeline

**Step 3: IA & Edição**
- SSE streaming mostra progresso do pipeline em tempo real
- Se houver lacunas: mostra perguntas A/B/C para o médico
- Após geração: revela texto com animação
- Área editável com `quickCheck` automático (debounce 2s)
- Mostra: checklist, audit log, compliance score, uso de tokens

**Step 4: Revisão & PDF**
- Resumo do relatório
- Navega para `/reports/:id/review` para download

---

## 6. Pipeline Multi-Agente (Core do Produto)

Este é o coração do sistema. O pipeline gera a justificativa técnica em 4 camadas:

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  PESQUISADOR    │ ──▸ │   REDATOR    │ ──▸ │   AUDITOR    │ ──▸ │  VALIDADOR   │
│  (Agente A)     │     │  (Agente B)  │     │  (Agente C)  │     │  (Camada 4)  │
│  GPT-4o         │     │  GPT-4o      │     │  GPT-4o      │     │  Python puro │
│                 │     │              │     │              │     │              │
│ • Busca evid.   │     │ • Redige     │     │ • Confere    │     │ • Regex      │
│ • PubMed        │     │ • Mimetiza   │     │ • Corrige    │     │ • Dados fixos│
│ • Lacunas A/B/C │     │ • Estrutura  │     │ • Checklist  │     │ • Zero LLM   │
│ • Compliance    │     │ • Anti-glosa │     │ • Refs       │     │              │
└─────────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### Orquestrador (`pipeline.py`)

**`ReportPipeline`** é uma classe com sessões in-memory (`_sessions`):

```python
class PipelineSession:
    session_id: str
    step: str           # init → researching → questions → writing → auditing → validating → done
    product: Product
    template: ReportTemplate
    medico_inputs: dict  # cid, diagnostico, paciente_nome, etc.
    research_result: ResearchResult
    pending_questions: list[dict]
    draft: DraftReport
    audit_result: AuditResult
    clinical_evidences: list[dict]
    pubmed_evidences: list[dict]
    compliance_context: ComplianceContext
    usage: PipelineUsage
```

**Fluxo:**

1. `start()` → Busca evidências (internas + PubMed) → Compliance context → Pesquisador
2. Se há lacunas → retorna perguntas, status = `questions`
3. `answer()` → Recebe respostas, se todas respondidas → `_generate()`
4. `_generate()` → Redator → Auditor → Validador → Score → `done`

### Pesquisador (`researcher.py`)

- **Entrada:** Produto, diagnóstico, CID
- **Ações:**
  - `_fetch_clinical_evidences()` — busca no banco (tabela `clinical_evidences`)
  - `_fetch_pubmed_evidences()` — busca no PubMed via `pubmed_service.py`
  - `build_compliance_context()` — verifica DUT, TUSS, Anvisa
  - Chama GPT-4o com `RESEARCHER_SYSTEM` prompt
- **Saída:** `ResearchResult` com evidências, referências, lacunas (perguntas A/B/C), sugestão TUSS

### Redator (`writer.py`)

- **Entrada:** `ResearchResult`, produto, template, inputs do médico, evidências
- **Ações:**
  - Monta contexto: facts do produto + template DNA + evidências + inputs
  - Chama GPT-4o com `WRITER_SYSTEM` prompt
- **Saída:** `DraftReport` com `justificativa_completa`, `falha_terapeutica`, `risco_nao_realizacao`, `base_legal`, `referencias`
- **Regras do prompt (críticas):**
  - Mimetizar exemplos aprovados
  - Argumento de superioridade técnica
  - Cascata de degeneração
  - Argumento financeiro
  - Citação obrigatória de autores
  - Fundamentação legal separada

### Auditor (`auditor.py`)

- **Entrada:** `DraftReport`, produto
- **Ações:**
  - Confronta CADA dado técnico com ficha oficial do produto
  - Verifica referências (mantém se autor conhecido, remove se inventada)
  - Avalia checklist de 6 itens
- **Saída:** `AuditResult` com `texto_corrigido`, `aprovado`, `checklist`, `audit_log`, `referencias_validadas`

### Validador (`validator.py`)

- **Camada 4 — Python puro, zero LLM**
- Regex para extrair entidades técnicas do texto (viscosidade, peso molecular, concentração, registro Anvisa)
- Compara com dados oficiais do produto
- Severidade: `bloqueante` ou `alerta`
- Se bloqueante: relatório não pode ser aprovado

### Checklist de 6 Itens

| # | Item | Descrição |
|---|------|-----------|
| 1 | Diagnóstico | CID + descrição presentes |
| 2 | Justificativa Técnica | Diferenciais do material |
| 3 | Falha Terapêutica | Tratamento conservador que falhou |
| 4 | Risco da Não Realização | Consequências de não operar |
| 5 | Base Legal ANS | RN 395 citada |
| 6 | Referência Bibliográfica | Pelo menos 1 referência |

### Enriquecimento de Referências

`_enrich_references()` no pipeline transforma referências simples ("Altman et al., 2015") em objetos ricos:

```python
{
    "texto": "Altman et al., 2015",
    "source": "pubmed",
    "pmid": "25678901",
    "doi": "10.1016/j.joca.2015.03.014",
    "link": "https://pubmed.ncbi.nlm.nih.gov/25678901/"
}
```

---

## 7. Compliance ANS

### Visão Geral

A camada de compliance verifica conformidade regulatória com ANS (Agência Nacional de Saúde Suplementar) e atribui um score de completude documental.

### 3 Modos de Compliance

| Modo | Quando | Ações |
|------|--------|-------|
| `rol_dut` | Procedimento está no Rol E tem DUT | Avalia critérios da DUT com DSL |
| `cobertura_direta` | Procedimento está no Rol SEM DUT | Cobertura obrigatória, score alto |
| `fora_do_rol` | Procedimento NÃO está no Rol | Gera Dossiê de Exceção + Checklist STF |

### ComplianceContext (`compliance_layer.py`)

Orquestra 3 serviços e produz um contexto unificado:

```python
@dataclass
class ComplianceContext:
    mode: str              # rol_dut | fora_do_rol | cobertura_direta
    dut_rule: DutRule       # Regra DUT encontrada (ou None)
    dut_evaluation: DutEvaluation  # Resultado da avaliação DSL
    dut_suggestions: list[str]     # Sugestões para o médico
    tuss_validation: TussValidation
    anvisa_status: AnvisaStatusResult
    approval_score: ApprovalScore
    stf_checklist: dict     # Checklist STF (só em fora_do_rol)
    rol_alternatives: list  # Alternativas do Rol
```

### DUT Engine (`dut_engine.py`)

Motor que avalia critérios da DUT usando uma **DSL (Domain Specific Language)** em Python puro — zero LLM.

**Exemplo de DSL:**
```json
{
  "criterios": [
    {"id": "A", "tipo": "deterministico", "campo_paciente": "idade", "operador": ">=", "valor": 18},
    {"id": "B", "tipo": "deterministico", "campo_paciente": "imc", "operador": ">=", "valor": 35},
    {"id": "C", "tipo": "subjetivo", "descricao": "Motivação adequada", "requer_llm": true}
  ],
  "exclusoes": [
    {"id": "EX1", "campo_paciente": "finalidade", "operador": "==", "valor": "estetico"}
  ]
}
```

**Operadores:** `>=`, `<=`, `>`, `<`, `==`, `!=`, `in`, `not_in`, `contains`, `between`

**Tipos de critério:**
- `deterministico` → avaliado por Python (zero custo)
- `subjetivo` → marcado como `unknown` (delegado ao Auditor)
- `exclusao` → se ativada, bloqueia a cobertura

### TUSS Validator (`tuss_validator.py`)

- `validate_opme_code()` — Código TUSS 19 existe na base oficial?
- `validate_tiss_field()` — Código está no campo/guia correto? (regra crítica: TUSS 19 NUNCA em Honorários)
- `check_anvisa_status()` — Registro Anvisa ativo, vencido ou suspenso?

### Approval Score (`approval_score.py`)

Score de 0-100 com 4 componentes:

| Componente | Peso | Descrição |
|-----------|------|-----------|
| Aderência DUT | 0-40 | % critérios atendidos |
| Completude TISS/TUSS | 0-30 | Código válido, campo correto |
| Qualidade da Justificativa | 0-20 | Justificativa gerada + CID consistente |
| Robustez da Evidência | 0-10 | Quantidade e nível das evidências |

**Níveis:** alto (>=80), médio (60-79), baixo (40-59), crítico (<40)

**Regra de linguagem:** Score NUNCA usa "garantia de aprovação". Sempre "completude documental estimada".

### Checklist STF (ADI 7.265, 2025)

Aplicado no modo `fora_do_rol`. 5 critérios cumulativos:

| # | Critério | Tipo |
|---|---------|------|
| 1 | Prescrição por médico assistente | Automatizável |
| 2 | Sem negativa expressa pela ANS | **Declaratório** (não automatizável) |
| 3 | Sem alternativa terapêutica no Rol | Automatizável |
| 4 | Evidência científica de alto nível | Automatizável |
| 5 | Registro Anvisa ativo | Automatizável |

---

## 8. Banco de Dados

### Modelos Principais

```
┌──────────┐    ┌──────────────┐    ┌────────────────┐
│   User   │    │   Product    │    │ ReportTemplate │
│  (auth)  │    │  (OPME)      │    │  (DNA de tom)  │
└────┬─────┘    └──────┬───────┘    └───────┬────────┘
     │                 │                     │
     │    ┌────────────▼─────────────────────▼───┐
     └───▸│           Report                     │
          │  cid, diagnosis, justificativa_ia,   │
          │  falha_terapeutica, base_legal_ans,  │
          │  checklist_status, approval_score,   │
          │  compliance_mode, tuss_codes,        │
          │  referencias_bib, agent_audit_log    │
          └──────────────────────────────────────┘
```

### Tabelas Core

| Tabela | Campos-chave | Descrição |
|--------|-------------|-----------|
| `users` | id, email, hashed_password, role | Usuários (médico/distribuidor/admin) |
| `products` | id, nome, linha, viscosidade, peso_molecular, registro_anvisa, codigo_tuss_sugerido | Produtos OPME com dados técnicos oficiais |
| `report_templates` | produto_id, tom_de_voz, template_corpo, exemplos_aprovados | Templates por produto |
| `reports` | user_id, product_id, cid, diagnosis, justificativa_ia, checklist_status, approval_score | Relatórios gerados |
| `clinical_evidences` | cid, product_id, snippet, autor, ano | Evidências internas pré-validadas |
| `pubmed_cache` | pmid, cid, title, abstract, doi | Cache PubMed progressivo |
| `report_edits` | report_id, original_text, edited_text, diff_json | Edições para aprendizado |

### Tabelas ANS (Compliance)

| Tabela | Campos-chave | Fonte de dados |
|--------|-------------|----------------|
| `tuss_materials` | codigo_tuss (PK), nome, grupo, registro_anvisa | ETL: FTP ANS (TUSS.zip) |
| `rol_versions` | versao, rn_numeros, hash_arquivo | ETL: Excel Rol Anexo I |
| `dut_versions` | versao, rn_numeros, hash_arquivo | ETL: PDF DUT Anexo II |
| `rol_procedures` | codigo_procedimento, nome, tem_dut, dut_numero | ETL: Excel Rol |
| `dut_rules` | numero_dut, criterios_dsl (JSON), criterios_texto, revisado_humano | ETL: PDF DUT + GPT-4o |
| `anvisa_products` | registro, status, data_validade | ETL: API/Scraping Anvisa |
| `tiss_rules` | tipo_guia, campo, regra | Manual / ETL |

### Tabelas RPA (Cotações)

| Tabela | Descrição |
|--------|-----------|
| `portal_configs` | Configuração de portais de cotação |
| `portal_credentials` | Credenciais por tenant |
| `rpa_runs` | Execuções do robô |
| `quotes` | Cotações captadas |
| `quote_items` | Itens de cotação |
| `quote_attachments` | Anexos |
| `quote_budgets` | Orçamentos |

---

## 9. Fluxo End-to-End: Geração de Relatório

Este é o fluxo completo desde o clique do médico até o PDF:

```
1. FRONTEND                                    2. BACKEND
   ┌──────────────────────┐                       ┌──────────────────────┐
   │ ReportCreate Step 2  │                       │ POST /api/ai/        │
   │ "Gerar Justificativa"│──── SSE stream ──────▸│ start-report-stream  │
   └──────────────────────┘                       └──────────┬───────────┘
                                                             │
   ┌──────────────────────┐                       ┌──────────▼───────────┐
   │ PipelineProgress     │◂── event: step ──────│ ReportPipeline.start()│
   │ "Pesquisando..."     │                       │                      │
   │ "3 evidências..."    │                       │ 1. clinical_evidences │
   │ "Redigindo..."       │                       │ 2. pubmed_evidences   │
   └──────────────────────┘                       │ 3. compliance_context │
                                                  │ 4. research() [GPT]  │
                                                  └──────────┬───────────┘
                                                             │
   Se lacunas:                                               │
   ┌──────────────────────┐                       ┌──────────▼───────────┐
   │ PipelineQuestion     │◂── event: questions ──│ return {questions}    │
   │ "Qual foi o          │                       └──────────────────────┘
   │  tratamento prévio?" │                       
   │ (A) (B) (C)          │──── POST /answer ────▸ answer() → _generate()
   └──────────────────────┘                       
                                                  ┌──────────────────────┐
   ┌──────────────────────┐                       │ _generate():         │
   │ TextReveal           │◂── event: done ──────│  Writer [GPT-4o]     │
   │ (texto animado)      │                       │  Auditor [GPT-4o]    │
   │                      │                       │  Validator [Python]   │
   │ Checklist: 5/6 ✓     │                       │  approval_score()    │
   │ Score: 78/100        │                       │  _save_report()      │
   │ Audit: 1 correção    │                       └──────────────────────┘
   └──────────────────────┘                       

3. SALVAR
   _save_report() cria Report no banco com:
   - justificativa_ia (texto do Auditor)
   - materials (nome do produto)
   - tuss_codes (código do produto)
   - approval_score, compliance_mode
   - checklist_status, agent_audit_log
   - referencias_bib (enriquecidas com PMID/DOI)

4. DOWNLOAD PDF
   GET /api/reports/{id}/download?format=pdf
   → build_guia_pdf(report) → WeasyPrint → bytes
   → Template HTML com: cabeçalho, meta-grid, justificativa, base legal, referências
```

---

## 10. ETL de Dados Regulatórios

Scripts em `services/api/scripts/etl/` para popular tabelas de compliance.

### TUSS 19 (`download_tuss.py`)

```
FTP ANS → TUSS.zip → extract CSV (Tabela 19) → parse → TussMaterial
```

- Verifica `Last-Modified` do ZIP para cron automático
- Normaliza texto para busca (`display_normalized`, `manufacturer_normalized`)

### Rol Anexo I (`download_rol.py`)

```
gov.br → Anexo_I_Rol.xlsx → openpyxl parse → RolProcedure + RolVersion
```

- Extrai: código procedimento, nome, segmentação, vínculo com DUT

### DUT Anexo II (`parse_dut_pdf.py`)

```
gov.br → Anexo_II_DUT.pdf → pdfplumber → chunks por DUT
→ GPT-4o estrutura → JSON → DSL determinística → DutRule + DutVersion
```

Estratégia em 3 etapas:
1. **Segmentação determinística** — pdfplumber extrai texto, identifica âncoras "DUT n."
2. **Estruturação com LLM** — GPT-4o gera JSON com critérios + evidence spans
3. **Validação pós-LLM** — verifica se todo critério tem evidence span, idades são parseáveis

### Anvisa (`check_anvisa.py`)

```
API Anvisa → parse response → AnvisaProduct
```

- Status: ativo, vencido, suspenso, cancelado
- Impacto: registro vencido → approval score cai drasticamente

### Executar tudo

```bash
cd services/api
python3 scripts/etl/ingest_all.py        # TUSS + Rol
python3 scripts/etl/parse_dut_pdf.py      # DUT (requer OPENAI_API_KEY)
python3 scripts/etl/check_anvisa.py       # Anvisa
```

---

## 11. Módulo de Cotações (RPA)

Sistema paralelo de captação de cotações de portais de saúde via RPA (Robotic Process Automation).

### Fluxo

```
Portal de cotação → RPA Bot → POST /api/quotes/ingest → Quote + Items
→ Dashboard → Criar orçamento → Aprovar → Submeter ao portal
→ Webhook ERP para sincronização
```

### Rotas principais

| Endpoint | Descrição |
|----------|-----------|
| `POST /api/quotes/ingest` | RPA envia cotações captadas |
| `GET /api/quotes` | Lista com filtros (portal, status) |
| `POST /api/quotes/{id}/budget` | Cria orçamento |
| `POST /api/quotes/{id}/budget/{bid}/submit` | Submete ao portal |
| `POST /api/quotes/webhook/erp` | Webhook de sincronização ERP |

---

## 12. Testes

### Estrutura

```
services/api/tests/
├── conftest.py                    # Fixtures compartilhadas
├── etl/
│   ├── test_tuss_ingest.py        # Parse CSV TUSS
│   ├── test_rol_ingest.py         # Parse Excel Rol
│   ├── test_dut_parser.py         # Parse PDF DUT
│   └── test_anvisa_checker.py     # Consulta Anvisa
├── services/
│   ├── test_dut_engine.py         # DSL determinística
│   ├── test_tuss_validator.py     # Validação TUSS/TISS
│   └── test_approval_score.py     # Score de aprovação
└── agents/
    ├── test_pipeline_dut.py       # Pipeline modo Rol/DUT
    ├── test_pipeline_fora_rol.py  # Modo Fora do Rol
    └── test_edge_cases_dut.py     # Edge cases DUT
```

### Executar

```bash
cd services/api
python3 -m pytest tests/ -v             # Testes unitários
python3 scripts/test_generate.py         # Teste em massa (10 cenários)
python3 scripts/test_compliance_full.py  # Teste compliance ANS
```

### Princípios

- **Determinísticos e offline** — CI roda sem rede, sem API externa
- **Downloads mockados** — Fixtures locais simulam TUSS.zip, Rol.xlsx, DUT.pdf
- **Idempotência** — ETLs testados rodando 2x (não duplica dados)
- **Monotonicidade do score** — Mais dados completos → score não cai
- **Sem linguagem de garantia** — Asserts verificam ausência de "garantido", "certeza"

---

## 13. Deploy e CI

### GitHub Actions (`.github/workflows/ci.yml`)

**Job `web`:**
- Node 20
- `npm ci` + `npm run build:web`

**Job `api`:**
- Python 3.11
- PostgreSQL 16 (service container)
- Instala dependências de sistema (WeasyPrint: libgobject, libpango, etc.)
- `create_tables` + `seed`
- Sobe uvicorn, health check
- Roda testes

### Para produção (futuro)

O projeto ainda não tem deploy de produção configurado. A arquitetura permite:
- Backend: Docker container com uvicorn + gunicorn
- Frontend: Build estático (Vite) servido por CDN/nginx
- Banco: PostgreSQL managed (RDS, Cloud SQL, etc.)
- ETLs: Cron job ou Cloud Scheduler

---

## Glossário

| Termo | Significado |
|-------|-------------|
| **OPME** | Órteses, Próteses e Materiais Especiais |
| **Glosa** | Negativa/recusa de pagamento por convênio |
| **ANS** | Agência Nacional de Saúde Suplementar |
| **TUSS** | Terminologia Unificada da Saúde Suplementar |
| **TUSS 19** | Tabela 19 do TUSS — materiais e OPME |
| **Rol** | Lista de procedimentos de cobertura obrigatória da ANS |
| **DUT** | Diretriz de Utilização — critérios condicionantes para cobertura |
| **TISS** | Padrão de Troca de Informação de Saúde Suplementar |
| **Anvisa** | Agência Nacional de Vigilância Sanitária |
| **STF** | Supremo Tribunal Federal |
| **STJ** | Superior Tribunal de Justiça |
| **RN** | Resolução Normativa da ANS |
| **DSL** | Domain Specific Language (linguagem de domínio para regras DUT) |
| **RAG** | Retrieval-Augmented Generation |
| **SVF** | Fração Vascular Estromal (tipo de enxerto) |
| **RPA** | Robotic Process Automation |
