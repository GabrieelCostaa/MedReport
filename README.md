# Assistente de Relatórios OPME

Plataforma SaaS B2B para geração automatizada de justificativas técnicas de OPME (Órteses, Próteses e Materiais Especiais), com inteligência artificial multi-agente que minimiza glosas de convênios médicos.

O sistema gera relatórios técnicos persuasivos, fundamentados em evidências científicas verificadas e conformes com a legislação vigente (RN 395/ANS), reduzindo o tempo de elaboração de horas para minutos.

## Arquitetura

```
Hugo/
├── apps/web/          → Frontend React + Chakra UI (Vite)
├── services/api/      → Backend FastAPI (Python)
├── services/rpa/      → Robô de captura de cotações (Playwright)
├── docker-compose.yml → PostgreSQL + Redis + Elasticsearch
└── turbo.json         → Orquestrador de monorepo (Turborepo)
```

### Pipeline Multi-Agente

```
                    ┌─────────────┐
    Dados do    │  Pesquisador  │   Busca evidências internas + PubMed
    Médico ───▶ │   (Agente A)  │   Identifica lacunas → perguntas A/B/C
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Redator   │   Gera justificativa técnica completa
                    │  (Agente B) │   Citações nominais, tom persuasivo
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   Auditor   │   Confronta dados com base oficial do produto
                    │  (Agente C) │   Corrige divergências, valida checklist
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Validador  │   Regex + Python puro (sem IA)
                    │  (Camada 4) │   Última barreira contra alucinações
                    └─────────────┘
```

## Stack

| Camada | Tecnologias |
|--------|-------------|
| **Frontend** | React 18, TypeScript, Chakra UI, Vite, React Router |
| **Backend** | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2 |
| **IA** | OpenAI GPT-4o, pipeline multi-agente, RAG |
| **Banco** | PostgreSQL 16 |
| **Cache** | Redis 7 |
| **Busca** | Elasticsearch 8.11, PubMed E-utilities API |
| **Documentos** | WeasyPrint (PDF), python-docx (DOCX), Jinja2 |
| **Infra** | Docker Compose, Turborepo |

## Funcionalidades

- **Geração com IA multi-agente** — pipeline de 4 camadas que pesquisa, redige, audita e valida
- **Imunidade a alucinações** — validador hard-coded (Python puro) confronta dados técnicos com base oficial do produto
- **Perguntas A/B/C** — quando há lacunas, o sistema pergunta ao médico com opções pré-formatadas
- **Evidências PubMed** — busca automática de artigos científicos com cache progressivo
- **Referências verificáveis** — cada citação inclui DOI/PMID com link direto e QR code no PDF
- **Progresso em tempo real** — Server-Sent Events com mensagens contextuais durante a geração
- **Escrita ao vivo** — o texto da justificativa aparece palavra por palavra na tela
- **Checklist de conformidade** — 6 itens obrigatórios validados em tempo real
- **Auditoria transparente** — log humanizado de correções com antes/depois
- **Exportação profissional** — PDF (WeasyPrint) e DOCX (python-docx) com formatação médica
- **Loop de aprendizagem** — captura silenciosa de edições do médico para aprender terminologia por especialidade
- **Rastreamento de custos** — tokens e custo (USD/BRL) por agente, visível ao médico
- **Busca reativa de produtos** — resultados aparecem enquanto o médico digita

## Requisitos

- Node.js 18+
- Python 3.11+
- Docker e Docker Compose

## Setup

### 1. Infraestrutura

```bash
docker compose up -d
```

Sobe PostgreSQL (porta 5432), Redis (6379) e Elasticsearch (9200).

### 2. Backend

```bash
cd services/api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Criar arquivo `.env`:

```env
DATABASE_URL=postgresql+asyncpg://opme:opme_dev_secret@localhost:5432/opme
REDIS_URL=redis://localhost:6379/0
ELASTICSEARCH_URL=http://localhost:9200
SECRET_KEY=sua-chave-secreta
OPENAI_API_KEY=sk-...
```

Criar tabelas e popular dados:

```bash
python3 scripts/seed_estudos_completo.py
```

Iniciar o servidor:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend

```bash
cd apps/web
npm install
npm run dev
```

Acesse `http://localhost:3000`.

## Scripts

| Script | Descrição |
|--------|-----------|
| `seed_estudos_completo.py` | Popula evidências clínicas (Lipedema, Ortopedia, Rec. Mama, Regenerativa) |
| `seed_estudos_estetica.py` | Popula evidências de estética (Laser, Enxerto) |
| `ingest_reports.py` | Ingere relatórios aprovados como templates |
| `update_tuss.py` | Atualiza tabela TUSS a partir de CSV/ANS |
| `test_generate.py` | Gera relatórios de teste em lote |
| `test_pubmed_unit.py` | Testes unitários do PubMed |
| `test_pubmed_integration.py` | Testes de integração do pipeline com PubMed |

## Variáveis de Ambiente

| Variável | Obrigatória | Descrição |
|----------|:-----------:|-----------|
| `DATABASE_URL` | Sim | Connection string do PostgreSQL |
| `REDIS_URL` | Sim | URL do Redis |
| `SECRET_KEY` | Sim | Chave para JWT |
| `OPENAI_API_KEY` | Sim | Chave da API OpenAI |
| `ELASTICSEARCH_URL` | Não | URL do Elasticsearch |
| `PUBMED_API_KEY` | Não | Chave da API PubMed (aumenta rate limit) |
| `PUBMED_ENABLED` | Não | Habilita busca PubMed (padrão: true) |
| `PUBMED_CACHE_TTL_DAYS` | Não | TTL do cache PubMed em dias (padrão: 180) |
| `INGEST_API_KEY` | Não | Token para robôs RPA enviarem cotações |

## API

A API está documentada automaticamente em:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Endpoints principais

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/api/ai/start-report-stream` | Inicia pipeline com SSE (tempo real) |
| `POST` | `/api/ai/answer-stream` | Envia respostas A/B/C com SSE |
| `POST` | `/api/ai/start-report` | Inicia pipeline (síncrono) |
| `POST` | `/api/ai/answer` | Envia respostas A/B/C (síncrono) |
| `POST` | `/api/ai/quick-check` | Checklist reativo (sem IA) |
| `POST` | `/api/ai/save-edit` | Captura edição do médico (learning loop) |
| `GET`  | `/api/ai/evidences-preview` | Preview de evidências por CID |
| `GET`  | `/api/ai/download-pdf/{id}` | Download do PDF do relatório |
| `GET`  | `/api/products` | Lista produtos OPME |
| `POST` | `/api/auth/login` | Autenticação |
| `POST` | `/api/auth/register` | Registro |

## Banco de Dados

| Tabela | Descrição |
|--------|-----------|
| `users` | Médicos e distribuidores |
| `products` | Produtos OPME com dados imutáveis (verdades absolutas) |
| `report_templates` | Templates DNA de relatórios aprovados |
| `reports` | Relatórios gerados |
| `clinical_evidences` | Evidências científicas pré-validadas por CID × Produto |
| `pubmed_cache` | Cache progressivo de artigos PubMed |
| `report_edits` | Edições capturadas para aprendizagem |
| `tuss_terms` | Terminologia TUSS |

## Licença

Proprietário. Todos os direitos reservados.
