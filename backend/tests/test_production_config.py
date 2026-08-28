import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import AppEnvironment, Settings, get_settings
from app.main import create_app


def production_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "app_env": "production",
        "debug": False,
        "database_url": "postgresql+asyncpg://app:private@db.internal/algoprofitx",
        "database_require_tls": True,
        "secret_key": "X6qvVf9mP2rL8sK4tN7wC3yH5jB0dG1z",
        "cors_allowed_origins": "https://www.algoprofitx.com",
        "frontend_public_url": "https://www.algoprofitx.com",
        "api_public_url": "https://api.algoprofitx.com",
        "market_data_provider": "synthetic",
        "_env_file": None,
    }
    values.update(overrides)
    return values


def assert_production_error(message: str, **overrides: object) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**production_values(**overrides))


def test_development_configuration_remains_usable():
    settings = Settings(
        database_url="postgresql+asyncpg://app:local@localhost/app",
        secret_key="local-secret",
        _env_file=None,
    )
    assert settings.app_env is AppEnvironment.DEVELOPMENT
    assert settings.debug is True
    assert settings.api_docs_enabled is True
    assert settings.database_connect_args == {}


def test_test_configuration_remains_usable():
    settings = Settings(
        app_env="test",
        database_url="postgresql+asyncpg://app:test@localhost/app_test",
        secret_key="test-secret",
        _env_file=None,
    )
    assert settings.app_env is AppEnvironment.TEST
    assert settings.api_docs_enabled is True


def test_valid_production_configuration_is_fail_closed_by_default():
    settings = Settings(**production_values())
    assert settings.app_env is AppEnvironment.PRODUCTION
    assert settings.api_docs_enabled is False
    assert settings.database_echo is False
    assert settings.database_connect_args == {"ssl": True}
    assert settings.market_data_provider == "synthetic"


def test_production_sql_echo_remains_off_even_if_debug_is_mutated():
    settings = Settings(**production_values())
    settings.debug = True
    assert settings.database_echo is False


def test_production_debug_is_rejected():
    assert_production_error("DEBUG must be false", debug=True)


@pytest.mark.parametrize(
    "secret",
    (
        "",
        "short",
        "replace-with-a-production-secret-value",
        "ci-only-secret-not-for-production",
    ),
)
def test_production_weak_or_placeholder_secret_is_rejected(secret: str):
    assert_production_error("SECRET_KEY", secret_key=secret)


def test_secret_and_database_url_representations_are_redacted():
    settings = Settings(**production_values())
    representation = repr(settings)
    assert settings.secret_key.get_secret_value() not in representation
    assert settings.database_url.get_secret_value() not in representation
    assert "**********" in representation


def test_production_wildcard_cors_is_rejected():
    assert_production_error(
        "must not contain", cors_allowed_origins="*,https://www.algoprofitx.com"
    )


def test_production_localhost_cors_is_rejected():
    assert_production_error(
        "must not be local",
        cors_allowed_origins="https://www.algoprofitx.com,http://localhost:5173",
    )


def test_production_requires_canonical_frontend_origin():
    assert_production_error(
        "must include https://www.algoprofitx.com",
        cors_allowed_origins="https://algoprofitx.com",
    )


def test_production_may_also_allow_apex_frontend_origin():
    settings = Settings(
        **production_values(
            cors_allowed_origins=(
                "https://www.algoprofitx.com",
                "https://algoprofitx.com",
            )
        )
    )
    assert "https://algoprofitx.com" in settings.cors_allowed_origins


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("frontend_public_url", "http://www.algoprofitx.com"),
        ("api_public_url", "http://api.algoprofitx.com"),
    ),
)
def test_insecure_production_public_url_is_rejected(field: str, value: str):
    assert_production_error("must use HTTPS", **{field: value})


def test_production_database_must_be_remote_asyncpg_with_tls():
    assert_production_error("DATABASE_REQUIRE_TLS", database_require_tls=False)
    assert_production_error(
        "must not target localhost",
        database_url="postgresql+asyncpg://app:private@localhost/algoprofitx",
    )
    assert_production_error(
        r"must use postgresql\+asyncpg",
        database_url="sqlite:///algoprofitx.db",
    )


@pytest.mark.asyncio
async def test_disabled_docs_are_not_public_but_schema_remains_programmatic(monkeypatch):
    for key, value in production_values().items():
        if key != "_env_file":
            monkeypatch.setenv(key.upper(), str(value))
    get_settings.cache_clear()
    application = create_app()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="https://api.algoprofitx.com"
        ) as client:
            assert (await client.get("/docs")).status_code == 404
            assert (await client.get("/redoc")).status_code == 404
            assert (await client.get("/openapi.json")).status_code == 404

        assert application.openapi()["info"]["title"] == "AlgoProfitX API"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_docs_remain_enabled_in_development(monkeypatch):
    monkeypatch.setenv("API_DOCS_ENABLED", "true")
    get_settings.cache_clear()
    application = create_app()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as client:
            assert (await client.get("/docs")).status_code == 200
            assert (await client.get("/openapi.json")).status_code == 200
    finally:
        get_settings.cache_clear()
