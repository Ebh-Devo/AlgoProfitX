import importlib.util
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import (
    APPROVED_PUBLIC_ORIGIN_PAIRS,
    CANONICAL_FRONTEND_ORIGIN,
    DEVELOPMENT_API_ORIGIN,
    DEVELOPMENT_FRONTEND_ORIGIN,
    PRODUCTION_API_ORIGIN,
    Settings,
    get_settings,
)
from app.main import create_app
from tests.test_production_config import production_values

REPO_ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENTS = json.loads((REPO_ROOT / "frontend" / "environments.json").read_text())


def development_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "app_env": "development",
        "database_url": "postgresql+asyncpg://app:local@db.internal/app",
        "secret_key": "local-secret",
        "cors_allowed_origins": DEVELOPMENT_FRONTEND_ORIGIN,
        "frontend_public_url": DEVELOPMENT_FRONTEND_ORIGIN,
        "api_public_url": DEVELOPMENT_API_ORIGIN,
        "_env_file": None,
    }
    values.update(overrides)
    return values


def test_backend_origins_match_the_frontend_environment_table():
    dev, prod = ENVIRONMENTS["development"], ENVIRONMENTS["production"]
    assert DEVELOPMENT_FRONTEND_ORIGIN == dev["webOrigin"]
    assert DEVELOPMENT_API_ORIGIN in dev["allowedUpstreamApiOrigins"]
    assert CANONICAL_FRONTEND_ORIGIN == prod["webOrigin"]
    assert PRODUCTION_API_ORIGIN in prod["allowedUpstreamApiOrigins"]


def test_development_origins_are_exact_https_without_wildcards():
    for origin in (DEVELOPMENT_FRONTEND_ORIGIN, DEVELOPMENT_API_ORIGIN):
        assert origin.startswith("https://")
        assert "*" not in origin
        assert origin.endswith(".development.catalystappsail.in")


def test_development_accepts_exact_development_frontend_origin():
    settings = Settings(**development_values())
    assert settings.cors_allowed_origins == (DEVELOPMENT_FRONTEND_ORIGIN,)


@pytest.mark.parametrize(
    "origins",
    [
        "*",
        "https://www.algoprofitx.com",
        "http://localhost:5173",
        f"{DEVELOPMENT_FRONTEND_ORIGIN},https://www.algoprofitx.com",
        "https://algoprofitx-web-50045554365.catalystappsail.in",
        "https://evil.example",
    ],
)
def test_deployed_development_rejects_unrelated_cors_origins(origins: str):
    with pytest.raises(ValidationError, match="exactly the Catalyst Development web origin"):
        Settings(**development_values(cors_allowed_origins=origins))


def test_deployed_development_rejects_a_foreign_frontend_url():
    with pytest.raises(ValidationError, match="FRONTEND_PUBLIC_URL"):
        Settings(**development_values(frontend_public_url="https://www.algoprofitx.com"))


def test_local_development_is_unaffected():
    settings = Settings(
        database_url="postgresql+asyncpg://app:local@localhost/app",
        secret_key="local-secret",
        cors_allowed_origins="http://localhost:5173",
        _env_file=None,
    )
    assert settings.cors_allowed_origins == ("http://localhost:5173",)


def test_development_pair_is_not_approved_for_production():
    assert (DEVELOPMENT_FRONTEND_ORIGIN, DEVELOPMENT_API_ORIGIN) not in APPROVED_PUBLIC_ORIGIN_PAIRS
    assert all(DEVELOPMENT_API_ORIGIN != api for _, api in APPROVED_PUBLIC_ORIGIN_PAIRS)


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "cors_allowed_origins": DEVELOPMENT_FRONTEND_ORIGIN,
            "frontend_public_url": DEVELOPMENT_FRONTEND_ORIGIN,
            "api_public_url": DEVELOPMENT_API_ORIGIN,
        },
        {"api_public_url": DEVELOPMENT_API_ORIGIN},
        {"cors_allowed_origins": f"https://www.algoprofitx.com,{DEVELOPMENT_FRONTEND_ORIGIN}"},
    ],
)
def test_production_cannot_be_configured_with_development_origins(overrides: dict):
    with pytest.raises(ValidationError):
        Settings(**production_values(**overrides))


def test_production_cors_rules_are_unchanged():
    settings = Settings(**production_values())
    assert settings.cors_allowed_origins == ("https://www.algoprofitx.com",)


@pytest.mark.asyncio
async def test_development_cors_allows_only_the_development_frontend(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", DEVELOPMENT_FRONTEND_ORIGIN)
    monkeypatch.setenv("FRONTEND_PUBLIC_URL", DEVELOPMENT_FRONTEND_ORIGIN)
    monkeypatch.setenv("API_PUBLIC_URL", DEVELOPMENT_API_ORIGIN)
    get_settings.cache_clear()
    try:
        app = create_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

            async def preflight(origin: str):
                return await client.options(
                    "/health",
                    headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
                )

            allowed = await preflight(DEVELOPMENT_FRONTEND_ORIGIN)
            for other in (
                "https://www.algoprofitx.com",
                "https://evil.example",
                "https://algoprofitx-web-50045554365.catalystappsail.in",
            ):
                assert (await preflight(other)).status_code == 400
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == DEVELOPMENT_FRONTEND_ORIGIN
    finally:
        get_settings.cache_clear()


def load_frontend_server(monkeypatch, app_env: str | None):
    if app_env is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", app_env)
    spec = importlib.util.spec_from_file_location(
        "frontend_server", REPO_ROOT / "frontend" / "server.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_development_csp_allows_only_the_exact_development_api(monkeypatch):
    csp = load_frontend_server(monkeypatch, "development").CSP
    assert f"connect-src 'self' {DEVELOPMENT_API_ORIGIN};" in csp
    assert PRODUCTION_API_ORIGIN not in csp
    assert "*" not in csp


def test_production_csp_keeps_the_production_api_origin(monkeypatch):
    csp = load_frontend_server(monkeypatch, "production").CSP
    assert f"connect-src 'self' {PRODUCTION_API_ORIGIN};" in csp
    assert "catalystappsail" not in csp


@pytest.mark.parametrize("app_env", [None, "", "staging", "Production"])
def test_frontend_server_fails_closed_without_a_known_environment(monkeypatch, app_env):
    with pytest.raises(RuntimeError, match="APP_ENV"):
        load_frontend_server(monkeypatch, app_env)
