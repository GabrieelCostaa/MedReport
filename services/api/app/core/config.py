from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://opme:opme_dev_secret@localhost:5432/opme"
    REDIS_URL: str = "redis://localhost:6379/0"
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
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

    # ANS Data Sources
    ANS_TUSS_FTP_URL: str = "https://dadosabertos.ans.gov.br/FTP/PDA/terminologia_unificada_saude_suplementar_TUSS/TUSS.zip"
    ANS_ROL_XLSX_URL: str = "https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/atualizacao-do-rol-de-procedimentos/Anexo_I_Rol_2021RN_465.2021_RN643.2025.xlsx/@@download/file"
    ANS_DUT_PDF_URL: str = "https://www.gov.br/ans/pt-br/acesso-a-informacao/participacao-da-sociedade/atualizacao-do-rol-de-procedimentos/Anexo_II_DUT_2021_RN_465.2021_RN628.2025_RN629.2025.pdf/@@download/file"
    ANS_DATA_DIR: str = "data/ans"

    class Config:
        env_file = ".env"


settings = Settings()
