import io
import json
import logging
import re
from pathlib import Path

import certifi

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import health
from app.core.config import Settings
from app.core.metrics import InMemoryMetrics, NoOpMetrics, set_metrics
from app.core.observability import JsonFormatter, log_event, request_id_context
from app.main import create_app


@pytest.mark.asyncio
async def test_liveness_is_dependency_free_and_legacy_alias_remains(monkeypatch):
    async def forbidden(_: float) -> bool:
        raise AssertionError("liveness must not touch the database")

    monkeypatch.setattr(health, "database_ready", forbidden)
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        for path in ("/health", "/health/live"):
            response = await client.get(path)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            assert "database" not in response.text.casefold()


@pytest.mark.asyncio
async def test_readiness_success_and_sanitized_failure(monkeypatch):
    application = create_app()

    async def ready(_: float) -> bool:
        return True

    monkeypatch.setattr(health, "database_ready", ready)
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        assert (await client.get("/health/ready")).json() == {"status": "ok"}

    async def unavailable(_: float) -> bool:
        return False

    monkeypatch.setattr(health, "database_ready", unavailable)
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
    assert "postgres" not in response.text.casefold()


@pytest.mark.asyncio
async def test_readiness_succeeds_against_isolated_test_database():
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_request_ids_are_generated_preserved_and_malformed_values_replaced():
    application = create_app()
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        generated = await client.get("/health/live")
        assert re.fullmatch(r"[0-9a-f-]{36}", generated.headers["X-Request-ID"])

        valid = await client.get("/health/live", headers={"X-Request-ID": "caller-123.trace"})
        assert valid.headers["X-Request-ID"] == "caller-123.trace"

        for malformed in ("x" * 65, "bad value"):
            replaced = await client.get("/health/live", headers={"X-Request-ID": malformed})
            assert replaced.headers["X-Request-ID"] != malformed
            assert re.fullmatch(r"[0-9a-f-]{36}", replaced.headers["X-Request-ID"])


def test_production_json_and_development_console_defaults(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    common = {
        "database_url": "postgresql+asyncpg://app:test@localhost/test",
        "secret_key": "test-secret",
        "_env_file": None,
    }
    assert Settings(**common).log_format == "console"
    production = Settings(
        app_env="production",
        debug=False,
        database_url="postgresql+asyncpg://app:private@db.internal/algoprofitx",
        database_require_tls=True,
        pgsslrootcert=Path(certifi.where()),
        secret_key="X6qvVf9mP2rL8sK4tN7wC3yH5jB0dG1z",
        cors_allowed_origins="https://www.algoprofitx.com",
        frontend_public_url="https://www.algoprofitx.com",
        api_public_url="https://api.algoprofitx.com",
        auth_cookie_secure=True,
        auth_csrf_cookie_domain="algoprofitx.com",
        backtest_execution_mode="disabled",
        _env_file=None,
    )
    assert production.log_format == "json"


def test_supported_logging_helper_redacts_representative_secrets():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("app.redaction_test")
    logger.handlers[:] = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    token = request_id_context.set("request-safe")
    try:
        log_event(
            "redaction_test",
            logger_name=logger.name,
            authorization="Bearer jwt.secret.value",
            cookie="refresh=raw-refresh-value",
            password="submitted-password",
            database_url="postgresql+asyncpg://user:db-secret@db.internal/app",
            safe_id="public-id",
        )
    finally:
        request_id_context.reset(token)
    payload = json.loads(stream.getvalue())
    rendered = stream.getvalue()
    assert payload["request_id"] == "request-safe"
    assert payload["safe_id"] == "public-id"
    for secret in ("jwt.secret.value", "raw-refresh-value", "submitted-password", "db-secret"):
        assert secret not in rendered


@pytest.mark.asyncio
async def test_unexpected_exception_is_sanitized_and_references_request_id(monkeypatch):
    recorded: list[tuple[str, dict]] = []

    def capture(event: str, **fields):
        recorded.append((event, fields))

    monkeypatch.setattr("app.main.log_event", capture)
    application = create_app()

    @application.get("/test-crash")
    async def crash():
        raise RuntimeError("private failure detail")

    async with AsyncClient(
        transport=ASGITransport(app=application, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        response = await client.get("/test-crash", headers={"X-Request-ID": "crash-reference"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "request_id": "crash-reference"}
    assert "private failure detail" not in response.text
    failure = next(fields for event, fields in recorded if event == "unexpected_server_error")
    assert failure["request_id"] == "crash-reference"
    assert failure["exc_info"] is True


@pytest.mark.asyncio
async def test_http_and_readiness_metrics_are_observed(monkeypatch):
    recorder = InMemoryMetrics()
    set_metrics(recorder)

    async def unavailable(_: float) -> bool:
        return False

    monkeypatch.setattr(health, "database_ready", unavailable)
    try:
        application = create_app()
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            await client.get("/health/live")
            await client.get("/health/ready")
    finally:
        set_metrics(NoOpMetrics())

    names = {name for name, _ in recorder.counters}
    assert "http.requests" in names
    assert "readiness.failures" in names
    assert any(name == "http.duration_ms" for name, _, _ in recorder.observations)
