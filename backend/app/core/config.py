import base64
import binascii
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
import ssl
from typing import Annotated, Literal, Self
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import PositiveFloat, PositiveInt, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
CANONICAL_FRONTEND_ORIGIN = "https://www.algoprofitx.com"
PRODUCTION_API_ORIGIN = "https://api.algoprofitx.com"
STAGING_FRONTEND_ORIGIN = "https://staging.algoprofitx.com"
STAGING_API_ORIGIN = "https://api-staging.algoprofitx.com"
# Deployed Zoho Catalyst Development AppSails. These must never appear in the
# production approved pairs below; the test suite checks this table against the
# frontend's environments.json.
DEVELOPMENT_FRONTEND_ORIGIN = (
    "https://algoprofitx-web-50045554365.development.catalystappsail.in"
)
DEVELOPMENT_API_ORIGIN = (
    "https://algoprofitx-api-50045554365.development.catalystappsail.in"
)
APPROVED_PUBLIC_ORIGIN_PAIRS = {
    (CANONICAL_FRONTEND_ORIGIN, PRODUCTION_API_ORIGIN),
    (STAGING_FRONTEND_ORIGIN, STAGING_API_ORIGIN),
}


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
    pgsslrootcert: Path | None = None
    pgsslrootcert_b64: SecretStr | None = None
    db_pool_size: PositiveInt = 5
    db_max_overflow: int = 2
    db_pool_timeout_seconds: PositiveInt = 10
    db_pool_recycle_seconds: PositiveInt = 1800
    db_pool_pre_ping: bool = True
    db_external_transaction_pooler: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["console", "json"] | None = None
    readiness_db_timeout_seconds: PositiveFloat = 2.0
    request_id_header: str = "X-Request-ID"

    secret_key: SecretStr
    access_token_expire_minutes: int = 30
    auth_jwt_issuer: str = "algoprofitx-api"
    auth_jwt_audience: str = "algoprofitx-web"
    auth_jwt_key_id: str = "primary"
    refresh_token_expire_days: PositiveInt = 30
    auth_max_sessions_per_user: PositiveInt = 5
    auth_refresh_cookie_name: str = "algoprofitx_refresh"
    auth_csrf_cookie_name: str = "algoprofitx_csrf"
    auth_cookie_secure: bool = False
    auth_cookie_httponly: bool = True
    auth_cookie_samesite: Literal["strict", "lax", "none"] = "strict"
    auth_cookie_path: str = "/api/v1/auth"
    auth_cookie_domain: str | None = None
    auth_csrf_cookie_path: str = "/"
    auth_csrf_cookie_domain: str | None = None
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
    definition_validation_burst_limit: PositiveInt = 20
    definition_validation_burst_window_seconds: PositiveInt = 60
    definition_validation_sustained_limit: PositiveInt = 300
    definition_validation_sustained_window_seconds: PositiveInt = 3600
    execution_burst_limit: PositiveInt = 10
    execution_burst_window_seconds: PositiveInt = 60
    execution_sustained_limit: PositiveInt = 60
    execution_sustained_window_seconds: PositiveInt = 3600
    backtest_max_concurrency_per_user: PositiveInt = 1
    backtest_execution_mode: Literal["inline", "disabled"] = "inline"

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

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: object) -> object:
        """Adapt provider PostgreSQL URIs to SQLAlchemy's asyncpg dialect."""
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw, str):
            return value
        parsed = urlsplit(raw)
        if parsed.scheme not in {"postgresql", "postgres"}:
            return value
        query = urlencode(
            [
                (key, item)
                for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                if key not in {"sslmode", "sslrootcert"}
            ]
        )
        return urlunsplit(
            ("postgresql+asyncpg", parsed.netloc, parsed.path, query, parsed.fragment)
        )

    @field_validator("request_id_header")
    @classmethod
    def validate_request_id_header(cls, value: str) -> str:
        if not value or len(value) > 64 or not all(
            character.isalnum() or character == "-" for character in value
        ):
            raise ValueError("REQUEST_ID_HEADER must be a valid bounded HTTP header name")
        return value

    @model_validator(mode="after")
    def enforce_environment_policy(self) -> Self:
        if self.db_max_overflow < 0:
            raise ValueError("DB_MAX_OVERFLOW must be greater than or equal to 0")
        if self.api_docs_enabled is None:
            self.api_docs_enabled = self.app_env is not AppEnvironment.PRODUCTION
        if self.log_format is None:
            self.log_format = (
                "json" if self.app_env is AppEnvironment.PRODUCTION else "console"
            )

        if (
            self.app_env is AppEnvironment.DEVELOPMENT
            and self.api_public_url.rstrip("/") == DEVELOPMENT_API_ORIGIN
        ):
            self._enforce_deployed_development_origins()

        if self.app_env is not AppEnvironment.PRODUCTION:
            return self

        errors: list[str] = []
        if self.debug:
            errors.append("DEBUG must be false in production")
        if not self.abuse_protection_enabled:
            errors.append("ABUSE_PROTECTION_ENABLED must be true in production")
        if not self.auth_cookie_secure:
            errors.append("AUTH_COOKIE_SECURE must be true in production")
        if not self.auth_cookie_httponly:
            errors.append("AUTH_COOKIE_HTTPONLY must be true in production")
        if self.auth_cookie_path != "/api/v1/auth":
            errors.append("AUTH_COOKIE_PATH must be /api/v1/auth in production")
        if self.auth_cookie_domain is not None:
            errors.append("AUTH_COOKIE_DOMAIN must be unset for a host-only refresh cookie")
        if self.auth_csrf_cookie_path != "/":
            errors.append("AUTH_CSRF_COOKIE_PATH must be / in production")
        if self.auth_csrf_cookie_domain != "algoprofitx.com":
            errors.append(
                "AUTH_CSRF_COOKIE_DOMAIN must be algoprofitx.com in production"
            )
        if not self.auth_jwt_issuer.strip() or not self.auth_jwt_audience.strip():
            errors.append("JWT issuer and audience must be configured in production")
        if self.access_token_expire_minutes > 30:
            errors.append("ACCESS_TOKEN_EXPIRE_MINUTES must not exceed 30 in production")
        if self.refresh_token_expire_days > 90:
            errors.append("REFRESH_TOKEN_EXPIRE_DAYS must not exceed 90 in production")

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
        frontend_origin = self.frontend_public_url.rstrip("/")
        api_origin = self.api_public_url.rstrip("/")
        if frontend_origin not in self.cors_allowed_origins:
            errors.append("CORS_ALLOWED_ORIGINS must include FRONTEND_PUBLIC_URL")
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

        if (frontend_origin, api_origin) not in APPROVED_PUBLIC_ORIGIN_PAIRS:
            errors.append("FRONTEND_PUBLIC_URL and API_PUBLIC_URL must be an approved pair")
        allowed_cors_origins = {frontend_origin}
        if frontend_origin == CANONICAL_FRONTEND_ORIGIN:
            allowed_cors_origins.add("https://algoprofitx.com")
        unexpected_origins = set(self.cors_allowed_origins) - allowed_cors_origins
        if unexpected_origins:
            errors.append("CORS_ALLOWED_ORIGINS contains an unapproved production origin")

        database_url = self.database_url.get_secret_value()
        parsed_database_url = urlsplit(database_url)
        if parsed_database_url.scheme != "postgresql+asyncpg":
            errors.append("DATABASE_URL must use postgresql+asyncpg in production")
        if parsed_database_url.hostname in {"localhost", "127.0.0.1", "::1"}:
            errors.append("DATABASE_URL must not target localhost in production")
        if not self.database_require_tls:
            errors.append("DATABASE_REQUIRE_TLS must be true in production")
        if self.pgsslrootcert is None and self.pgsslrootcert_b64 is None:
            errors.append(
                "PGSSLROOTCERT or PGSSLROOTCERT_B64 is required in production"
            )
        if self.backtest_execution_mode != "disabled":
            errors.append(
                "BACKTEST_EXECUTION_MODE must be disabled until a durable worker is configured"
            )

        if errors:
            raise ValueError("; ".join(errors))
        return self

    def _enforce_deployed_development_origins(self) -> None:
        """The deployed Development API accepts browsers from exactly one origin."""
        if self.frontend_public_url.rstrip("/") != DEVELOPMENT_FRONTEND_ORIGIN:
            raise ValueError(
                "FRONTEND_PUBLIC_URL must be the Catalyst Development web origin"
            )
        if set(self.cors_allowed_origins) != {DEVELOPMENT_FRONTEND_ORIGIN}:
            raise ValueError(
                "CORS_ALLOWED_ORIGINS must be exactly the Catalyst Development web origin"
            )

    @property
    def database_echo(self) -> bool:
        """SQL logging is never permitted in production."""
        return self.debug and self.app_env is not AppEnvironment.PRODUCTION

    @property
    def database_connect_args(self) -> dict[str, object]:
        """Build a certificate-verifying asyncpg TLS context without writing CA data."""
        if not self.database_require_tls:
            return {}
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = True
        if self.pgsslrootcert is not None:
            context.load_verify_locations(cafile=self.pgsslrootcert)
        elif self.pgsslrootcert_b64 is not None:
            encoded = self.pgsslrootcert_b64.get_secret_value().strip()
            try:
                decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise ValueError(
                    "PGSSLROOTCERT_B64 must contain valid Base64 PEM data"
                ) from exc
            try:
                context.load_verify_locations(cadata=decoded)
            except ssl.SSLError as exc:
                raise ValueError(
                    "PGSSLROOTCERT_B64 must contain a valid CA certificate"
                ) from exc
        return {"ssl": context}

    @property
    def uses_application_pool(self) -> bool:
        """Only production application processes keep a persistent connection pool."""
        return (
            self.app_env is AppEnvironment.PRODUCTION
            and not self.db_external_transaction_pooler
        )

    @property
    def database_engine_options(self) -> dict[str, object]:
        options: dict[str, object] = {
            "echo": self.database_echo,
            "connect_args": self.database_connect_args,
        }
        if self.uses_application_pool:
            options.update(
                pool_size=self.db_pool_size,
                max_overflow=self.db_max_overflow,
                pool_timeout=self.db_pool_timeout_seconds,
                pool_recycle=self.db_pool_recycle_seconds,
                pool_pre_ping=self.db_pool_pre_ping,
            )
        return options


@lru_cache
def get_settings() -> Settings:
    return Settings()
