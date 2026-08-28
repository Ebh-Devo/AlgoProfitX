from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import PositiveInt, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
CANONICAL_FRONTEND_ORIGIN = "https://www.algoprofitx.com"
PRODUCTION_API_ORIGIN = "https://api.algoprofitx.com"


class AppEnvironment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    app_name: str = "AlgoProfitX"
    app_env: AppEnvironment = AppEnvironment.DEVELOPMENT
    debug: bool = True

    database_url: SecretStr
    database_require_tls: bool = False

    secret_key: SecretStr
    access_token_expire_minutes: int = 30
    cors_allowed_origins: Annotated[tuple[str, ...], NoDecode] = ()
    frontend_public_url: str = "http://localhost:5173"
    api_public_url: str = "http://127.0.0.1:8000"
    api_docs_enabled: bool | None = None

    abuse_protection_enabled: bool = True
    login_ip_limit: PositiveInt = 10
    login_ip_window_seconds: PositiveInt = 60
    login_account_limit: PositiveInt = 20
    login_account_window_seconds: PositiveInt = 900
    registration_ip_limit: PositiveInt = 20
    registration_ip_window_seconds: PositiveInt = 3600
    creator_enrollment_limit: PositiveInt = 3
    creator_enrollment_window_seconds: PositiveInt = 3600
    backtest_burst_limit: PositiveInt = 5
    backtest_burst_window_seconds: PositiveInt = 60
    backtest_sustained_limit: PositiveInt = 30
    backtest_sustained_window_seconds: PositiveInt = 3600
    execution_burst_limit: PositiveInt = 10
    execution_burst_window_seconds: PositiveInt = 60
    execution_sustained_limit: PositiveInt = 60
    execution_sustained_window_seconds: PositiveInt = 3600
    backtest_max_concurrency_per_user: PositiveInt = 1

    redis_url: str = "redis://localhost:6379/0"
    market_data_provider: str = "synthetic"
    market_data_timeout_seconds: float = 15.0
    market_data_max_retries: int = 2
    market_data_max_range_days: int = 3660
    market_data_max_candles: int = 4000

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

    @model_validator(mode="after")
    def enforce_environment_policy(self) -> Self:
        if self.api_docs_enabled is None:
            self.api_docs_enabled = self.app_env is not AppEnvironment.PRODUCTION

        if self.app_env is not AppEnvironment.PRODUCTION:
            return self

        errors: list[str] = []
        if self.debug:
            errors.append("DEBUG must be false in production")
        if not self.abuse_protection_enabled:
            errors.append("ABUSE_PROTECTION_ENABLED must be true in production")

        secret = self.secret_key.get_secret_value().strip()
        normalized_secret = secret.lower()
        placeholder_markers = (
            "placeholder",
            "replace-with",
            "changeme",
            "change-me",
            "example",
            "development-secret",
            "test-only",
            "ci-only",
        )
        if not secret:
            errors.append("SECRET_KEY must not be blank in production")
        elif len(secret.encode("utf-8")) < 32:
            errors.append("SECRET_KEY must contain at least 32 bytes in production")
        elif any(marker in normalized_secret for marker in placeholder_markers):
            errors.append("SECRET_KEY must not use a placeholder or development value")

        if "*" in self.cors_allowed_origins:
            errors.append("CORS_ALLOWED_ORIGINS must not contain '*' in production")
        if CANONICAL_FRONTEND_ORIGIN not in self.cors_allowed_origins:
            errors.append(
                f"CORS_ALLOWED_ORIGINS must include {CANONICAL_FRONTEND_ORIGIN}"
            )
        for origin in self.cors_allowed_origins:
            parsed = urlsplit(origin)
            if parsed.scheme != "https":
                errors.append(f"Production CORS origin must use HTTPS: {origin}")
            if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
                errors.append(f"Production CORS origin must not be local: {origin}")

        for field_name, public_url in (
            ("FRONTEND_PUBLIC_URL", self.frontend_public_url),
            ("API_PUBLIC_URL", self.api_public_url),
        ):
            if urlsplit(public_url).scheme != "https":
                errors.append(f"{field_name} must use HTTPS in production")

        if self.frontend_public_url.rstrip("/") != CANONICAL_FRONTEND_ORIGIN:
            errors.append(
                f"FRONTEND_PUBLIC_URL must be {CANONICAL_FRONTEND_ORIGIN} in production"
            )
        if self.api_public_url.rstrip("/") != PRODUCTION_API_ORIGIN:
            errors.append(f"API_PUBLIC_URL must be {PRODUCTION_API_ORIGIN} in production")

        database_url = self.database_url.get_secret_value()
        parsed_database_url = urlsplit(database_url)
        if parsed_database_url.scheme != "postgresql+asyncpg":
            errors.append("DATABASE_URL must use postgresql+asyncpg in production")
        if parsed_database_url.hostname in {"localhost", "127.0.0.1", "::1"}:
            errors.append("DATABASE_URL must not target localhost in production")
        if not self.database_require_tls:
            errors.append("DATABASE_REQUIRE_TLS must be true in production")

        if errors:
            raise ValueError("; ".join(errors))
        return self

    @property
    def database_echo(self) -> bool:
        """SQL logging is never permitted in production."""
        return self.debug and self.app_env is not AppEnvironment.PRODUCTION

    @property
    def database_connect_args(self) -> dict[str, object]:
        """Require encrypted asyncpg transport when configured."""
        return {"ssl": True} if self.database_require_tls else {}


@lru_cache
def get_settings() -> Settings:
    return Settings()
