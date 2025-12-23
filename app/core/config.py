from __future__ import annotations

from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # =====================================================
    # APP
    # =====================================================
    app_name: str = "Lights Backend"
    app_env: str = "local"
    log_level: str = "INFO"

    # =====================================================
    # REDIS
    # =====================================================
    redis_url: str = "redis://localhost:6379/0"

    # =====================================================
    # MONGO
    # =====================================================
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "lights"

    # =====================================================
    # MEDIA
    # =====================================================
    media_dir: str = "./media"

    # =====================================================
    # PIPELINE
    # =====================================================
    pipeline_concurrency: int = 1
    pipeline_job_timeout_s: int = 900  # 15 min

    # =====================================================
    # OPENAI
    # =====================================================
    openai_api_key: str = Field(default="", repr=False)
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.4
    openai_max_tokens: int = 1200
    openai_timeout_s: int = 45

    # =====================================================
    # Pydantic config
    # =====================================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore", 
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()