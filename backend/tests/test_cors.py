import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import create_app


def test_cors_allowed_origins_parses_comma_separated_values(monkeypatch):
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173, https://app.example.test/",
    )
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.cors_allowed_origins == (
            "http://localhost:5173",
            "https://app.example.test",
        )
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_cors_allows_only_configured_origin(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173")
    get_settings.cache_clear()
    cors_app = create_app()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=cors_app),
            base_url="http://test",
        ) as client:
            allowed = await client.options(
                "/health",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
            denied = await client.options(
                "/health",
                headers={
                    "Origin": "http://untrusted.example",
                    "Access-Control-Request-Method": "GET",
                },
            )

        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "access-control-allow-credentials" not in allowed.headers
        assert denied.status_code == 400
    finally:
        get_settings.cache_clear()
