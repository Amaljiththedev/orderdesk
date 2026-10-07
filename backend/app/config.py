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
    JWT_SECRET: str = "change-me"


@lru_cache
def get_settings() -> Settings:
    """Read settings once and reuse them (cached)."""
    return Settings()
