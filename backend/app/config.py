"""App settings, read from environment variables (and .env for local runs).

Docker Compose sets DATABASE_URL for the container; everything else comes from .env.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://orderdesk:orderdesk@localhost:5433/orderdesk"
    GROQ_API_KEY: str = ""
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    LLM_MODEL: str = "openai/gpt-oss-120b"
    LLM_FALLBACK_MODEL: str = "llama-3.3-70b-versatile"
    LLM_TIMEOUT_S: float = 60.0
    EMBED_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBED_DIM: int = 384
    ENV: str = "dev"                      # dev | prod
    JWT_SECRET: str = "change-me"
    ACCESS_TOKEN_MINUTES: int = 15
    REFRESH_TOKEN_DAYS: int = 14
    MAX_FAILED_LOGINS: int = 5
    LOCKOUT_MINUTES: int = 15
    # lines at or above this match confidence are auto-approved (chosen from evals/match_eval.py:
    # 99.3% precision, 74% auto-approved on the generated set; see docs/decisions.md)
    AUTO_APPROVE_THRESHOLD: float = 0.5
    ERP_URL: str = "http://localhost:8002"
    ERP_TIMEOUT_S: float = 2.0
    ERP_RETRIES: int = 4


@lru_cache
def get_settings() -> Settings:
    """Read settings once and reuse them (cached)."""
    s = Settings()
    if s.ENV != "dev" and (s.JWT_SECRET == "change-me" or len(s.JWT_SECRET) < 32):
        raise RuntimeError("JWT_SECRET must be set to a long random value outside dev")
    return s
