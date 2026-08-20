from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "TradeEBH"
    app_env: str = "development"
    debug: bool = True

    database_url: str

    secret_key: str
    access_token_expire_minutes: int = 30

    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        # Keep the local configuration next to the backend, independent of
        # whether Uvicorn, Alembic, or pytest is launched from the repo root.
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
