from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Dict


def _parse_esp_registry(value: str) -> Dict[str, str]:
    """
    ESP_REGISTRY format:
      "right=192.168.0.50,left=192.168.0.51"
    """
    out: Dict[str, str] = {}
    if not value:
        return out
    pairs = [p.strip() for p in value.split(",") if p.strip()]
    for pair in pairs:
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[k.strip()] = v.strip()
    return out


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = Field(default="dev", alias="APP_ENV")
    app_name: str = Field(default="led-show-backend", alias="APP_NAME")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    mongo_url: str = Field(default="mongodb://localhost:27017", alias="MONGO_URL")
    mongo_db: str = Field(default="led_show", alias="MONGO_DB")

    media_dir: str = Field(default="./media", alias="MEDIA_DIR")
    ytdlp_bin: str = Field(default="yt-dlp", alias="YTDLP_BIN")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    esp_protocol: str = Field(default="http", alias="ESP_PROTOCOL")  # http or udp later
    esp_timeout_s: float = Field(default=2.0, alias="ESP_TIMEOUT_S")

    esp_registry_raw: str = Field(default="", alias="ESP_REGISTRY")

    @property
    def esp_registry(self) -> Dict[str, str]:
        return _parse_esp_registry(self.esp_registry_raw)


settings = Settings()
