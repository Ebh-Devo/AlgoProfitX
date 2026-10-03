import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_version_endpoint_returns_release_identity():
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/api/version")
    assert response.status_code == 200
    body = response.json()
    assert body["repository"] == "Ebh-Devo/AlgoProfitX"
    assert body["component"] == "algoprofitx-api"
    assert "sha" in body


@pytest.mark.asyncio
async def test_version_endpoint_reflects_env_sha(monkeypatch):
    monkeypatch.setenv("APP_SOURCE_SHA", "abc1234def5678901234567890123456789012ab")
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/api/version")
    assert response.status_code == 200
    assert response.json()["sha"] == "abc1234def5678901234567890123456789012ab"


@pytest.mark.asyncio
async def test_version_endpoint_does_not_expose_secrets(monkeypatch):
    monkeypatch.setenv("APP_SOURCE_SHA", "deadbeef" * 5)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:secret@host/db")
    monkeypatch.setenv("SECRET_KEY", "supersecret")
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/api/version")
    body = response.text
    assert "secret" not in body.lower()
    assert "database" not in body.lower()
    assert "password" not in body.lower()
