import sys
from urllib.parse import urlparse
from pydantic_settings import BaseSettings
from typing import List

_WEAK_KEYS = {"dev-secret-change-in-production", "secret", "changeme", ""}


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://opme:opme_dev_secret@localhost:5432/opme"
    REDIS_URL: str = "redis://localhost:6379/0"
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    SECRET_KEY: str  # Obrigatório — defina via variável de ambiente ou .env
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 dia — reduzir para 30 min ao implementar refresh token
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    OPENAI_API_KEY: str = ""
    INGEST_API_KEY: str = ""  # Token para RPA/robôs enviarem cotações (opcional)
    API_BASE_URL: str = "http://localhost:8000"  # URL base para links de verificação (override em produção)

    # PubMed E-utilities
    PUBMED_API_KEY: str = ""
    PUBMED_CACHE_TTL_DAYS: int = 180
    PUBMED_MAX_RESULTS: int = 10
    PUBMED_TIMEOUT_SECONDS: int = 15
    PUBMED_ENABLED: bool = True

    # ANVISA API Gateway (OAuth2 Client Credentials)
    ANVISA_CLIENT_ID: str = ""
    ANVISA_CLIENT_SECRET: str = ""
    ANVISA_TOKEN_URL: str = "https://acesso.prd.apps.anvisa.gov.br/auth/realms/externo/protocol/openid-connect/token"
    ANVISA_GATEWAY_URL: str = "https://api-gateway.prd.apps.anvisa.gov.br/consultas-externas-api/api/v1"
    ANVISA_TIMEOUT: int = 15

    # UMLS Terminology Services (for Medical Knowledge Graph)
    UMLS_API_KEY: str = ""
    UMLS_BASE_URL: str = "https://uts-ws.nlm.nih.gov/rest"

    # ANS Data Sources
    ANS_TUSS_FTP_URL: str = "https://dadosabertos.ans.gov.br/FTP/PDA/terminologia_unificada_saude_suplementar_TUSS/TUSS.zip"
    ANS_ROL_XLSX_URL: str = "https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/atualizacao-do-rol-de-procedimentos/Anexo_I_Rol_2021RN_465.2021_RN643.2025.xlsx/@@download/file"
    ANS_DUT_PDF_URL: str = "https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/atualizacao-do-rol-de-procedimentos/Anexo_II_DUT_2021_RN_465.2021_RN628.2025_RN629.2025.pdf/@@download/file"
    ANS_DATA_DIR: str = "data/ans"

    class Config:
        env_file = ".env"


settings = Settings()

_parsed_base = urlparse(settings.API_BASE_URL)
if not _parsed_base.scheme or not _parsed_base.netloc:
    print(
        f"\n[SEGURANÇA] API_BASE_URL inválida: '{settings.API_BASE_URL}'\n"
        "Defina uma URL completa, ex.: http://localhost:8000 ou https://api.dominio.com\n",
        file=sys.stderr,
    )
    sys.exit(1)

if settings.SECRET_KEY in _WEAK_KEYS or len(settings.SECRET_KEY) < 32:
    print(
        "\n[SEGURANÇA] SECRET_KEY ausente, vazia ou fraca (< 32 caracteres).\n"
        "Defina uma chave forte em .env: SECRET_KEY=<string aleatória de 64+ chars>\n",
        file=sys.stderr,
    )
    sys.exit(1)
