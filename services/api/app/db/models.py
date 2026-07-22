from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Text, ForeignKey,
    Enum as SQLEnum, TypeDecorator, JSON, Float, Integer, Index, LargeBinary,
)
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
    # Dados profissionais do médico
    nome = Column(String(255), nullable=True)
    crm = Column(String(50), nullable=True)
    crm_uf = Column(String(2), nullable=True)
    rqe = Column(String(50), nullable=True)  # Registro de Qualificação de Especialista
    # Identidade da clínica/emissor (timbrado do PDF)
    clinica_nome = Column(String(255), nullable=True)
    clinica_logo_url = Column(String(500), nullable=True)
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
    # Proveniência dos campos de ficha técnica acima: quais foram gerados por
    # LLM, extraídos de bula em PDF ou copiados da ANVISA — e quando. Sem isto
    # é impossível distinguir dado oficial de texto que a própria IA escreveu,
    # e o Auditor acaba validando o laudo contra a saída de outro modelo.
    # NULL = origem desconhecida/legado (NUNCA interpretar como "revisado").
    # Ver app/services/provenance.py.
    campos_gerados_ia = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ProductTussMapping(Base):
    """Mapeamento N:N entre Produto OPME e códigos TUSS de procedimentos aplicáveis."""
    __tablename__ = "product_tuss_mappings"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(), ForeignKey("products.id"), nullable=False, index=True)
    tuss_code = Column(String(20), nullable=False, index=True)
    procedure_name = Column(Text, nullable=False)
    subgroup = Column(String(255), nullable=True)
    applications = Column(Text, nullable=True)
    is_primary = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_product_tuss_unique", "product_id", "tuss_code", unique=True),
    )


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
    exemplos_aprovados = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(), ForeignKey("users.id"), nullable=False)
    product_id = Column(UUID(), ForeignKey("products.id"), nullable=True)
    status = Column(String(50), default="draft")  # draft | generating | review | approved | signed
    # Identificação
    paciente_nome = Column(String(255), nullable=True)
    paciente_dob = Column(String(20), nullable=True)  # data de nascimento (ISO ou dd/mm/aaaa)
    paciente_carteirinha = Column(String(60), nullable=True)  # nº da carteirinha do convênio
    paciente_cpf = Column(String(20), nullable=True)
    guia_numero = Column(String(60), nullable=True)  # nº da guia TISS
    atendimento_numero = Column(String(60), nullable=True)  # nº do atendimento
    especialidade = Column(String(100), nullable=True)
    cid = Column(String(20), nullable=True)
    cids_secundarios = Column(JSON, nullable=True)  # ["M17.1", "M25.5", ...]
    diagnosis = Column(Text, nullable=True)
    surgery_description = Column(Text, nullable=True)
    materials = Column(Text, nullable=True)
    materiais_tuss = Column(JSON, nullable=True)  # [{"codigo": "...", "nome": "...", "qtd": 1}]
    health_plan = Column(String(255), nullable=True)
    operadora_registro_ans = Column(String(20), nullable=True)  # registro ANS resolvido do convênio
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
    # ANS Compliance: versões usadas na geração (auditoria reprodutível)
    rol_version_id = Column(UUID(), ForeignKey("rol_versions.id"), nullable=True)
    dut_version_id = Column(UUID(), ForeignKey("dut_versions.id"), nullable=True)
    tuss_version = Column(String(20), nullable=True)
    approval_score = Column(Float, nullable=True)
    approval_score_details = Column(JSON, nullable=True)
    compliance_mode = Column(String(50), nullable=True)  # rol_dut | fora_do_rol | cobertura_direta
    compliance_texto = Column(Text, nullable=True)  # seção "Adequação Rol/DUT" do PDF
    # Desfecho real na operadora (loop de prova de valor) — capturado semanas
    # após o envio; cruzado com approval_score prova que o score prediz aprovação.
    outcome = Column(String(20), default="pendente")  # pendente | aprovado | glosado | parcial
    outcome_at = Column(DateTime(timezone=True), nullable=True)
    outcome_motivo_codigo = Column(String(10), nullable=True)  # TISS Tabela 38 (quando glosado)
    outcome_notes = Column(Text, nullable=True)
    # Sinais de geração (antes computados e descartados) — custo, tokens por
    # agente e raciocínio do Auditor; alimentam análise de qualidade e custo.
    token_cost_usd = Column(Float, nullable=True)
    token_usage_json = Column(JSON, nullable=True)
    auditor_cot = Column(Text, nullable=True)
    # Verificador de fidelidade (decompose-then-verify) — modo "flag": mede e
    # anota, nunca altera o texto. score = afirmações sustentadas / verificáveis.
    faithfulness_score = Column(Float, nullable=True)
    faithfulness_flags = Column(JSON, nullable=True)
    # Métricas de qualidade RAGAS-style (juiz LLM barato)
    quality_faithfulness = Column(Float, nullable=True)
    quality_relevancy = Column(Float, nullable=True)
    quality_citation = Column(Float, nullable=True)
    quality_details = Column(JSON, nullable=True)
    # Assinatura
    signed_at = Column(DateTime(timezone=True), nullable=True)
    # Snapshot dos dados do médico no momento da assinatura
    medico_nome = Column(String(255), nullable=True)
    medico_crm = Column(String(50), nullable=True)
    medico_crm_uf = Column(String(2), nullable=True)
    signature_hash = Column(String(64), nullable=True)
    # PDF selado gerado no momento da assinatura (imutável)
    pdf_signed_bytes = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class ClinicalEvidence(Base):
    """Evidências científicas pré-validadas por CID x Produto. O Pesquisador busca aqui antes de tudo."""
    __tablename__ = "clinical_evidences"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    cid = Column(String(20), nullable=False, index=True)
    product_id = Column(UUID(), ForeignKey("products.id"), nullable=False, index=True)
    snippet = Column(Text, nullable=False)
    autor = Column(String(255), nullable=False)
    referencia_completa = Column(Text, nullable=True)
    ano = Column(String(10), nullable=True)
    tipo = Column(String(50), nullable=True)  # meta-analise | rct | revisao | coorte
    relevancia = Column(String(20), default="alta")  # alta | media | baixa
    doi = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class PubmedCache(Base):
    """Cache permanente de artigos PubMed buscados via E-utilities."""
    __tablename__ = "pubmed_cache"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    pmid = Column(String(20), unique=True, nullable=False, index=True)
    cid = Column(String(20), nullable=False, index=True)
    search_term = Column(String(500), nullable=False)
    title = Column(Text, nullable=False)
    authors = Column(Text, nullable=False)
    first_author = Column(String(255), nullable=False)
    year = Column(String(10), nullable=False)
    journal = Column(String(500), nullable=True)
    abstract = Column(Text, nullable=True)
    article_type = Column(String(50), nullable=True)
    doi = Column(String(255), nullable=True)
    relevance_score = Column(String(10), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ReportEdit(Base):
    """Captura edições do médico sobre texto gerado pela IA para aprendizagem."""
    __tablename__ = "report_edits"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    report_id = Column(UUID(), ForeignKey("reports.id"), nullable=False, index=True)
    user_id = Column(UUID(), ForeignKey("users.id"), nullable=False, index=True)
    especialidade = Column(String(100), nullable=True)
    original_text = Column(Text, nullable=False)
    edited_text = Column(Text, nullable=False)
    diff_json = Column(JSON, nullable=True)
    edit_type = Column(String(50), nullable=True)  # terminology | structure | addition | removal
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TussTerm(Base):
    __tablename__ = "tuss_terms"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), nullable=False, index=True)
    term = Column(Text, nullable=False)
    table_source = Column(String(50), nullable=True)  # e.g. procedimentos, materiais
    version = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ---------------------------------------------------------------------------
# ANS Compliance Models
# ---------------------------------------------------------------------------

class AnvisaStatus(str, enum.Enum):
    ativo = "ativo"
    vencido = "vencido"
    suspenso = "suspenso"
    cancelado = "cancelado"


class TussProcedure(Base):
    """TUSS Tabela 22 - Procedimentos e Eventos em Saúde. Fonte: FTP ANS."""
    __tablename__ = "tuss_procedures"

    codigo_tuss = Column(String(20), primary_key=True)
    nome = Column(Text, nullable=False)
    display_normalized = Column(Text, nullable=True, index=True)
    grupo = Column(String(255), nullable=True)
    ativo = Column(Boolean, default=True)
    versao_tuss = Column(String(100), nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class TussMaterial(Base):
    """TUSS Tabela 19 - Materiais e OPME. Fonte: FTP ANS."""
    __tablename__ = "tuss_materials"

    codigo_tuss = Column(String(20), primary_key=True)
    nome = Column(Text, nullable=False)
    display_normalized = Column(Text, nullable=True, index=True)
    grupo = Column(String(255), nullable=True)
    subgrupo = Column(String(255), nullable=True)
    fabricante = Column(String(255), nullable=True)
    manufacturer_normalized = Column(String(255), nullable=True, index=True)
    registro_anvisa = Column(String(50), nullable=True)
    descricao = Column(Text, nullable=True)
    ativo = Column(Boolean, default=True)
    data_atualizacao = Column(DateTime(timezone=True), nullable=True)
    versao_tuss = Column(String(100), nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class RolVersion(Base):
    """Versão do Rol de Procedimentos (Anexo I). Rastreabilidade de qual versão foi usada."""
    __tablename__ = "rol_versions"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    artifact_type = Column(String(20), default="rol")
    versao = Column(String(100), nullable=False)
    rn_numeros = Column(JSON, nullable=True)  # ["465/2021", "643/2025"]
    data_publicacao = Column(DateTime(timezone=True), nullable=True)
    data_vigencia = Column(DateTime(timezone=True), nullable=True)
    hash_arquivo = Column(String(64), nullable=True)
    url_fonte = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class DutVersion(Base):
    """Versão das DUT (Anexo II). Separado do Rol porque podem ser atualizados por RNs diferentes."""
    __tablename__ = "dut_versions"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    artifact_type = Column(String(20), default="dut")
    versao = Column(String(100), nullable=False)
    rn_numeros = Column(JSON, nullable=True)  # ["465/2021", "628/2025", "629/2025"]
    data_publicacao = Column(DateTime(timezone=True), nullable=True)
    data_vigencia = Column(DateTime(timezone=True), nullable=True)
    hash_arquivo = Column(String(64), nullable=True)
    url_fonte = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class RolProcedure(Base):
    """Procedimento do Rol da ANS (Anexo I). Define cobertura obrigatória por segmentação."""
    __tablename__ = "rol_procedures"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    codigo_procedimento = Column(String(50), nullable=False, index=True)
    nome = Column(Text, nullable=False)
    segmentacao_ambulatorial = Column(Boolean, default=False)
    segmentacao_hospitalar = Column(Boolean, default=False)
    segmentacao_obstetrica = Column(Boolean, default=False)
    segmentacao_odontologica = Column(Boolean, default=False)
    tem_dut = Column(Boolean, default=False)
    dut_numero = Column(String(20), nullable=True)
    grupo = Column(String(255), nullable=True)
    subgrupo = Column(String(255), nullable=True)
    version_id = Column(UUID(), ForeignKey("rol_versions.id"), nullable=True)
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_rol_proc_code_version", "codigo_procedimento", "version_id"),
    )


class DutRule(Base):
    """Diretriz de Utilização (Anexo II). Critérios condicionantes de cobertura."""
    __tablename__ = "dut_rules"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    numero_dut = Column(String(20), nullable=False, index=True)
    titulo = Column(Text, nullable=False)
    procedimento_nome = Column(Text, nullable=True)
    procedimento_codigo = Column(String(20), nullable=True, index=True)
    # Critérios: 3 representações complementares
    criterios_json = Column(JSON, nullable=True)    # GPT-4o output with evidence_spans
    criterios_texto = Column(Text, nullable=True)    # Texto original do PDF
    criterios_dsl = Column(JSON, nullable=True)      # DSL determinística para Python
    exames_exigidos = Column(JSON, nullable=True)
    documentos_exigidos = Column(JSON, nullable=True)
    faixa_etaria_min = Column(Integer, nullable=True)
    faixa_etaria_max = Column(Integer, nullable=True)
    condicoes_vedacao = Column(JSON, nullable=True)
    # Versionamento e rastreabilidade
    version_id = Column(UUID(), ForeignKey("dut_versions.id"), nullable=True)
    revisado_humano = Column(Boolean, default=False)
    source_url = Column(String(500), nullable=True)
    source_hash = Column(String(64), nullable=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    extraction_confidence = Column(Float, nullable=True)  # 0.0-1.0
    extraction_warnings = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_dut_numero_version", "numero_dut", "version_id"),
    )


class AnvisaProduct(Base):
    """Registro de produto na Anvisa. Critério 5 do STF (ADI 7.265)."""
    __tablename__ = "anvisa_products"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    registro = Column(String(50), nullable=False, unique=True, index=True)
    nome_comercial = Column(String(500), nullable=True)
    fabricante = Column(String(500), nullable=True)
    status = Column(SQLEnum(AnvisaStatus), default=AnvisaStatus.ativo)
    data_validade = Column(DateTime(timezone=True), nullable=True)
    classe_risco = Column(String(20), nullable=True)
    data_consulta = Column(DateTime(timezone=True), nullable=True)
    dados_json = Column(JSON, nullable=True)
    nome_tecnico = Column(String(500), nullable=True)
    modelos_descricao = Column(Text, nullable=True)
    # Busca sem acento em nome comercial + fabricante + nome técnico (indexado via pg_trgm)
    search_normalized = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class TissRule(Base):
    """Regra do TISS Organizacional. Define campos permitidos/proibidos por tipo de guia."""
    __tablename__ = "tiss_rules"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    tipo_guia = Column(String(100), nullable=False, index=True)
    campo = Column(String(100), nullable=False)
    regra = Column(String(50), nullable=False)  # permitido | proibido | obrigatorio
    tabela_tuss_aplicavel = Column(String(20), nullable=True)  # "19", "22", etc.
    descricao = Column(Text, nullable=True)
    versao_tiss = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_tiss_guia_campo", "tipo_guia", "campo"),
    )


class GlosaMotivo(Base):
    """TISS Tabela 38 — Terminologia de mensagens (motivos de glosa).

    Fonte: Padrão TISS, XLSX "TUSS - Demais terminologias" (aba Tab 38).
    Ingerida a partir de data/ans/tabela38_motivos_glosa.csv (extraído 1x
    via scripts/etl/extract_tabela38.py e versionado no repositório).
    """
    __tablename__ = "glosa_motivos"

    codigo = Column(String(10), primary_key=True)  # ex.: "1001"
    descricao = Column(Text, nullable=False)
    descricao_normalized = Column(Text, nullable=True, index=True)
    vigencia_inicio = Column(DateTime(timezone=True), nullable=True)
    vigencia_fim = Column(DateTime(timezone=True), nullable=True)
    ativo = Column(Boolean, default=True)  # False quando vigencia_fim já passou
    versao_tiss = Column(String(20), nullable=True)  # ex.: "202601"
    raw_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class OperadoraGlosaIndicador(Base):
    """Painel de Indicadores de Glosa da ANS (PDA-057), por operadora e mês.

    Snapshot completo recarregado atomicamente pelo ETL
    scripts/etl/download_glosa_panel.py (5 CSVs de dados abertos).
    """
    __tablename__ = "operadora_glosa_indicadores"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    registro_ans = Column(String(20), nullable=False, index=True)
    razao_social = Column(String(500), nullable=True)
    razao_social_normalized = Column(String(500), nullable=True, index=True)
    porte = Column(String(100), nullable=True)
    segmentacao = Column(String(255), nullable=True)
    modalidade = Column(String(255), nullable=True)
    periodo = Column(String(7), nullable=False, index=True)  # "2019-01"
    pc_glosa_inicial = Column(Float, nullable=True)  # %
    pc_glosa_final = Column(Float, nullable=True)  # %
    tempo_medio_pagamento_dias = Column(Float, nullable=True)
    numero_guias_sem_retorno = Column(Float, nullable=True)
    valor_guias_sem_retorno = Column(Float, nullable=True)  # R$
    dt_carga = Column(String(20), nullable=True)  # DT_CARGA da ANS
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_glosa_op_registro_periodo", "registro_ans", "periodo", unique=True),
    )


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


# ---------------------------------------------------------------------------
# LGPD Audit Trail
# ---------------------------------------------------------------------------

class AuditAction(str, enum.Enum):
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXPORT = "EXPORT"       # data portability (LGPD Art. 18)
    SIGN = "SIGN"           # electronic signature
    GENERATE = "GENERATE"   # AI report generation


class AuditLog(Base):
    """
    LGPD audit trail: tracks WHO accessed/modified WHAT data WHEN.
    Required for compliance with LGPD Art. 37 (controller must demonstrate compliance).
    Retention: 5 years (logs), 20 years (reports).
    """
    __tablename__ = "audit_log"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    # WHO
    user_id = Column(UUID, ForeignKey("users.id"), nullable=True, index=True)
    user_crm = Column(String(20), nullable=True)
    user_ip = Column(String(45), nullable=True)

    # WHAT
    action = Column(SQLEnum(AuditAction), nullable=False)
    resource_type = Column(String(100), nullable=False, index=True)  # "report", "patient"
    resource_id = Column(String(255), nullable=True, index=True)

    # DETAILS
    changes = Column(JSON, nullable=True)  # {"field": {"old": x, "new": y}}
    justification = Column(Text, nullable=True)  # LGPD: legal basis for access
    metadata_ = Column("metadata", JSON, nullable=True)

    __table_args__ = (
        Index("ix_audit_resource", "resource_type", "resource_id"),
        Index("ix_audit_user_time", "user_id", "timestamp"),
    )


# ---------------------------------------------------------------------------
# Medical Knowledge Graph
# ---------------------------------------------------------------------------

class MedicalConcept(Base):
    """Node in the medical knowledge graph (3-tiered: domain → literature → ontology)."""
    __tablename__ = "medical_concepts"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), nullable=False, index=True)
    code_system = Column(String(30), nullable=False, index=True)  # ICD10, UMLS, SNOMED, TUSS, MESH, PRODUCT, ANVISA, EVIDENCE, PUBMED, DUT
    name = Column(String(500), nullable=False)
    name_en = Column(String(500), nullable=True)
    semantic_type = Column(String(100), nullable=True)  # Disease, Procedure, Device, Evidence, Literature, Regulatory, Substance
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_concept_code_system", "code", "code_system", unique=True),
    )


class ConceptRelation(Base):
    """Edge in the medical knowledge graph (adjacency list)."""
    __tablename__ = "concept_relations"

    id = Column(UUID(), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(), ForeignKey("medical_concepts.id"), nullable=False, index=True)
    target_id = Column(UUID(), ForeignKey("medical_concepts.id"), nullable=False, index=True)
    relation_type = Column(String(50), nullable=False, index=True)  # is_a, treats, indicated_for, has_procedure, has_evidence, maps_to, requires_dut, supported_by
    source_system = Column(String(30), nullable=True)
    confidence = Column(Float, default=1.0)
    metadata_ = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_rel_source_type", "source_id", "relation_type"),
        Index("ix_rel_target_type", "target_id", "relation_type"),
    )
