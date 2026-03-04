from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Enum as SQLEnum, TypeDecorator, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
import uuid
import enum

from app.db.session import Base


class UUID(TypeDecorator):
    """UUID type compatível com SQLite e PostgreSQL."""
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if isinstance(value, uuid.UUID):
                return str(value)
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if not isinstance(value, uuid.UUID):
                return uuid.UUID(value)
        return value

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(String(36))


def JSONType():
    """JSON type compatível com SQLite e PostgreSQL."""
    from sqlalchemy import JSON
    return JSON


class UserRole(str, enum.Enum):
    medico = "medico"
    distribuidor = "distribuidor"
    admin = "admin"


class LegalBasis(str, enum.Enum):
    """Bases legais para tratamento de dados sensíveis conforme LGPD Art. 11."""
    consent = "consent"  # Art. 11, I - Consentimento
    legal_obligation = "legal_obligation"  # Art. 11, II, a - Obrigação legal/regulatória (TISS/ANS)
    health_protection = "health_protection"  # Art. 11, II, f - Tutela da saúde
    vital_interests = "vital_interests"  # Art. 11, II, e - Proteção da vida
    contract_execution = "contract_execution"  # Art. 11, II, d - Execução de contrato


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.medico)
    # LGPD: registro de ciência das bases legais (não apenas consentimento)
    legal_basis_acknowledged = Column(Boolean, default=False)
    legal_basis_at = Column(DateTime(timezone=True), nullable=True)
    # Campos legados mantidos para migração (deprecated)
    consent_accepted = Column(Boolean, default=False)
    consent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class Product(Base):
    """Produto OPME com dados imutáveis (verdades absolutas). O Agente Auditor confronta o rascunho com estes dados."""
    __tablename__ = "products"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False, index=True)
    linha = Column(String(100), nullable=True)
    descricao_tecnica = Column(Text, nullable=True)
    diferenciais_clinicos = Column(Text, nullable=True)
    indicacoes = Column(Text, nullable=True)
    contraindicacoes = Column(Text, nullable=True)
    # Dados imutáveis (bula oficial)
    viscosidade = Column(String(100), nullable=True)
    peso_molecular = Column(String(100), nullable=True)
    concentracao = Column(String(100), nullable=True)
    registro_anvisa = Column(String(50), nullable=True)
    codigo_tuss_sugerido = Column(String(50), nullable=True)
    # Referências
    bula_url = Column(String(500), nullable=True)
    referencias_bibliograficas = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ReportTemplate(Base):
    """Template DNA de relatórios aprovados. Mimetiza tom, citações e bases legais de sucesso."""
    __tablename__ = "report_templates"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    nome = Column(String(255), nullable=False)
    especialidade = Column(String(100), nullable=True)
    produto_id = Column(UUID(), ForeignKey("products.id"), nullable=True)
    tom_de_voz = Column(Text, nullable=True)
    template_corpo = Column(Text, nullable=True)
    bases_legais = Column(JSON, nullable=True)
    referencias_padrao = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(), ForeignKey("users.id"), nullable=False)
    product_id = Column(UUID(), ForeignKey("products.id"), nullable=True)
    status = Column(String(50), default="draft")  # draft | generating | review | approved | signed
    # Identificação
    paciente_nome = Column(String(255), nullable=True)
    especialidade = Column(String(100), nullable=True)
    cid = Column(String(20), nullable=True)
    diagnosis = Column(Text, nullable=True)
    surgery_description = Column(Text, nullable=True)
    materials = Column(Text, nullable=True)
    health_plan = Column(String(255), nullable=True)
    tuss_codes = Column(JSON, nullable=True)
    # Campos gerados pelo pipeline multi-agente
    justificativa_ia = Column(Text, nullable=True)
    falha_terapeutica = Column(Text, nullable=True)
    risco_nao_realizacao = Column(Text, nullable=True)
    base_legal_ans = Column(Text, nullable=True)
    referencias_bib = Column(JSON, nullable=True)
    # Auditoria e checklist
    agent_audit_log = Column(JSON, nullable=True)
    checklist_status = Column(JSON, nullable=True)
    inconsistencies = Column(JSON, nullable=True)
    # Sessão de IA
    ai_session_id = Column(String(100), nullable=True)
    ai_session_data = Column(JSON, nullable=True)
    # Assinatura
    signed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class TussTerm(Base):
    __tablename__ = "tuss_terms"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), nullable=False, index=True)
    term = Column(Text, nullable=False)
    table_source = Column(String(50), nullable=True)  # e.g. procedimentos, materiais
    version = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class QuoteStatus(str, enum.Enum):
    """Status do ciclo de vida da cotação."""
    open = "open"  # Cotação aberta, aguardando resposta
    pending = "pending"  # Capturada, aguardando processamento
    draft = "draft"  # Orçamento em rascunho
    sent = "sent"  # Orçamento enviado
    won = "won"  # Cotação ganha
    lost = "lost"  # Cotação perdida
    expired = "expired"  # Prazo expirado
    closed = "closed"  # Fechada pelo portal


class BuyerType(str, enum.Enum):
    """Tipo de comprador."""
    operator = "operator"  # Operadora de plano
    hospital = "hospital"  # Hospital
    clinic = "clinic"  # Clínica
    platform = "platform"  # Plataforma/marketplace
    other = "other"


class RpaRunStatus(str, enum.Enum):
    """Status de execução RPA."""
    queued = "queued"
    running = "running"
    success = "success"
    partial = "partial"  # Sucesso parcial (alguns erros)
    failed = "failed"
    timeout = "timeout"
    cancelled = "cancelled"


class PortalConfig(Base):
    """Configuração de portal para RPA."""
    __tablename__ = "portal_configs"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=True)
    base_url = Column(String(500), nullable=False)
    login_url = Column(String(500), nullable=True)
    list_url = Column(String(500), nullable=True)
    auth_type = Column(String(50), default="password")  # password | sso | certificate | 2fa
    captcha_profile = Column(String(50), default="none")  # none | occasional | always
    selector_version = Column(String(20), default="v1")
    rate_limit_requests_per_minute = Column(String(10), default="10")
    retry_policy = Column(JSON, nullable=True)  # {max_attempts, backoff_seconds}
    enabled = Column(Boolean, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class PortalCredential(Base):
    """Referência a credenciais de portal (segredo fica em secrets manager)."""
    __tablename__ = "portal_credentials"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(100), nullable=False, index=True)
    portal_id = Column(UUID(as_uuid=True), ForeignKey("portal_configs.id"), nullable=False)
    secret_id = Column(String(255), nullable=False)  # Referência ao secrets manager
    username_hint = Column(String(100), nullable=True)  # Apenas para identificação, não a senha
    last_rotated_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class RpaRun(Base):
    """Registro de execução de robô RPA."""
    __tablename__ = "rpa_runs"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(100), nullable=True, index=True)
    portal_id = Column(UUID(as_uuid=True), ForeignKey("portal_configs.id"), nullable=True)
    portal_name = Column(String(100), nullable=True)
    # Execução
    status = Column(SQLEnum(RpaRunStatus), default=RpaRunStatus.queued)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(String(20), nullable=True)
    # Resultados
    quotes_found = Column(String(10), default="0")
    quotes_new = Column(String(10), default="0")
    items_captured = Column(String(10), default="0")
    attachments_downloaded = Column(String(10), default="0")
    pages_visited = Column(String(10), default="0")
    # Problemas
    captcha_encountered = Column(Boolean, default=False)
    login_failed = Column(Boolean, default=False)
    error_code = Column(String(50), nullable=True)
    error_message = Column(Text, nullable=True)
    # Retries
    attempt_number = Column(String(5), default="1")
    max_attempts = Column(String(5), default="3")
    # Auditoria
    job_config = Column(JSON, nullable=True)  # Configuração do job
    screenshots_refs = Column(JSON, nullable=True)  # URIs de screenshots
    logs_ref = Column(String(500), nullable=True)  # URI para logs detalhados
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Quote(Base):
    """Cotação capturada de portal."""
    __tablename__ = "quotes"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(String(100), nullable=True, index=True)
    portal_id = Column(UUID(as_uuid=True), ForeignKey("portal_configs.id"), nullable=True)
    portal = Column(String(255), nullable=False, index=True)  # Nome do portal (compatibilidade)
    external_id = Column(String(255), nullable=True, index=True)  # ID no portal (chave idempotente)
    status = Column(SQLEnum(QuoteStatus), default=QuoteStatus.pending)
    # Dados do comprador
    buyer_name = Column(String(255), nullable=True)
    buyer_type = Column(SQLEnum(BuyerType), nullable=True)
    # Datas
    published_at = Column(DateTime(timezone=True), nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=True)
    # Entrega
    delivery_city = Column(String(100), nullable=True)
    delivery_state = Column(String(50), nullable=True)
    delivery_notes = Column(Text, nullable=True)
    # Conteúdo
    description = Column(Text, nullable=True)
    notes_raw = Column(Text, nullable=True)
    currency = Column(String(10), default="BRL")
    # Metadados
    payload = Column(JSON, nullable=True)  # Dados brutos/extras
    raw_payload_ref = Column(String(500), nullable=True)  # URI para snapshot HTML/JSON
    rpa_run_id = Column(UUID(as_uuid=True), ForeignKey("rpa_runs.id"), nullable=True)
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # Chave única: portal + external_id para idempotência
        # Index("ix_quote_portal_external", "portal", "external_id", unique=True),
    )


class QuoteItem(Base):
    """Item de cotação (linha de produto)."""
    __tablename__ = "quote_items"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    quote_id = Column(UUID(as_uuid=True), ForeignKey("quotes.id"), nullable=False, index=True)
    line_no = Column(String(10), nullable=True)
    # Dados brutos do portal
    product_code_raw = Column(String(100), nullable=True)
    product_name_raw = Column(Text, nullable=True)
    # Normalização (preenchido após matching)
    normalized_sku = Column(String(100), nullable=True)
    normalized_name = Column(String(255), nullable=True)
    # Quantidades
    qty = Column(String(20), nullable=True)  # String para flexibilidade (ex: "2-5")
    uom = Column(String(50), nullable=True)  # Unidade de medida
    # Preferências
    brand_pref = Column(String(100), nullable=True)
    specs = Column(Text, nullable=True)
    comments = Column(Text, nullable=True)
    # Preços (opcional, se disponível no portal)
    reference_price = Column(String(50), nullable=True)
    # Resposta (orçamento)
    bid_price = Column(String(50), nullable=True)
    bid_lead_time_days = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class QuoteAttachment(Base):
    """Anexo de cotação (PDF, planilha, termo de referência)."""
    __tablename__ = "quote_attachments"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    quote_id = Column(UUID(as_uuid=True), ForeignKey("quotes.id"), nullable=False, index=True)
    item_id = Column(UUID(as_uuid=True), ForeignKey("quote_items.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=True)
    size_bytes = Column(String(20), nullable=True)
    storage_uri = Column(String(500), nullable=True)  # S3/GCS/local path
    sha256 = Column(String(64), nullable=True)
    downloaded_at = Column(DateTime(timezone=True), nullable=True)
    download_status = Column(String(50), default="pending")  # pending | success | failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class QuoteBudget(Base):
    """Orçamento/resposta para cotação."""
    __tablename__ = "quote_budgets"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    quote_id = Column(UUID(as_uuid=True), ForeignKey("quotes.id"), nullable=False, index=True)
    tenant_id = Column(String(100), nullable=True)
    # Itens do orçamento
    items = Column(JSON, nullable=True)  # [{product, price, qty, lead_time}, ...]
    total_value = Column(String(50), nullable=True)
    currency = Column(String(10), default="BRL")
    # Condições
    payment_terms = Column(String(255), nullable=True)
    delivery_days = Column(String(10), nullable=True)
    validity_days = Column(String(10), nullable=True)
    notes = Column(Text, nullable=True)
    # Status
    status = Column(String(50), default="draft")  # draft | approved | submitted | rejected
    approved_by = Column(String(255), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    submission_ref = Column(String(255), nullable=True)  # ID no portal após envio
    # ERP
    erp_synced = Column(Boolean, default=False)
    erp_sync_at = Column(DateTime(timezone=True), nullable=True)
    erp_reference = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
