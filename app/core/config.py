from __future__ import annotations

import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",  # ✅ para não quebrar quando você tiver variáveis a mais no .env
    )

    # app
    log_level: str = "INFO"
    app_env: str = "dev"

    # infra
    redis_url: str = "redis://localhost:6379/0"
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "lights"

    # pipeline
    pipeline_concurrency: int = 1
    pipeline_job_timeout_s: int = 300

    # media
    media_dir: str = "./media"
    cache_dir: str = "./.cache"

    # public base (para montar audioStreamUrl)
    public_base_url: str = "http://localhost:8000"

    # bins
    ytdlp_bin: str = "yt-dlp"
    ffmpeg_bin: str = "ffmpeg"
    ffmpeg_path: str = "/usr/local/bin/ffmpeg"

    # openai
    openai_api_key: str = ""
    openai_timeout_s: int = 45
    openai_model: str = "gpt-4o-mini"  # ajuste se quiser


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()