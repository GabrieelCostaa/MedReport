"""
Configuração centralizada do RPA.
"""
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RetryPolicy:
    """Política de retentativas."""
    max_attempts: int = 3
    backoff_seconds: list[int] = field(default_factory=lambda: [10, 60, 300])
    retry_on_captcha: bool = False
    retry_on_timeout: bool = True


@dataclass
class PortalConfig:
    """Configuração de um portal específico."""
    name: str
    display_name: str
    base_url: str
    login_url: Optional[str] = None
    list_url: Optional[str] = None
    auth_type: str = "password"  # password | sso | certificate | 2fa
    captcha_profile: str = "none"  # none | occasional | always
    rate_limit_rpm: int = 10
    timeout_seconds: int = 30
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    selectors: dict = field(default_factory=dict)
    enabled: bool = True


@dataclass
class RpaConfig:
    """Configuração global do RPA."""
    api_url: str = os.getenv("OPME_API_URL", "http://localhost:8000")
    api_token: str = os.getenv("OPME_API_TOKEN", "")
    storage_path: str = os.getenv("RPA_STORAGE_PATH", "/tmp/rpa_storage")
    screenshots_enabled: bool = os.getenv("RPA_SCREENSHOTS", "true").lower() == "true"
    headless: bool = os.getenv("RPA_HEADLESS", "true").lower() == "true"
    max_concurrent_jobs: int = int(os.getenv("RPA_MAX_CONCURRENT", "3"))
    default_timeout: int = int(os.getenv("RPA_DEFAULT_TIMEOUT", "30"))
    log_level: str = os.getenv("RPA_LOG_LEVEL", "INFO")


DEFAULT_CONFIG = RpaConfig()
