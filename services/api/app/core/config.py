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

    # PubMed E-utilities
    PUBMED_API_KEY: str = ""
    PUBMED_CACHE_TTL_DAYS: int = 180
    PUBMED_MAX_RESULTS: int = 10
    PUBMED_TIMEOUT_SECONDS: int = 5
    PUBMED_ENABLED: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
