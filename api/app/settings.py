from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Signal Signage API"
    environment: str = "development"
    database_url: str = "postgresql://signage:signage@db:5432/signage"
    redis_url: str = "redis://redis:6379/0"
    media_root: Path = Path("/data/media")
    backup_root: Path = Path("/data/backups")
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
