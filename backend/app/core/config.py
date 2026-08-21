from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "TradeEBH"
    app_env: str = "development"
    debug: bool = True

    database_url: str

    secret_key: str
    access_token_expire_minutes: int = 30
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()

    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        # Keep the local configuration next to the backend, independent of
        # whether Uvicorn, Alembic, or pytest is launched from the repo root.
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def parse_cors_allowed_origins(cls, value: object) -> tuple[str, ...]:
        """Accept a comma-separated environment variable without wildcard defaults."""
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            return tuple(
                origin.strip().rstrip("/")
                for origin in value.split(",")
                if origin.strip()
            )
        if isinstance(value, (list, tuple)):
            return tuple(str(origin).strip().rstrip("/") for origin in value)
        raise ValueError("CORS_ALLOWED_ORIGINS must be a comma-separated list")


@lru_cache
def get_settings() -> Settings:
    return Settings()
