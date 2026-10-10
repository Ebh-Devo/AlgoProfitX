"""The deployed runtime is Catalyst-only: no PostgreSQL driver, Alembic, Redis or fallback."""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
FORBIDDEN_PACKAGES = ("asyncpg", "alembic", "redis", "psycopg", "psycopg2", "pg8000", "aiopg")


def requirement_names(path: Path) -> set[str]:
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        names.add(re.split(r"[<>=!~\[; ]", line, maxsplit=1)[0].lower())
    return names


def test_production_manifest_has_no_postgresql_alembic_or_redis_packages():
    names = requirement_names(BACKEND / "requirements-production.txt")
    assert "zcatalyst-sdk" in names
    assert not names & set(FORBIDDEN_PACKAGES)


def test_development_manifest_no_longer_carries_redis():
    assert "redis" not in requirement_names(BACKEND / "requirements.txt")
    assert "redis" not in requirement_names(BACKEND / "requirements.lock")


def test_sqlalchemy_in_the_production_manifest_is_a_documented_exception():
    """SQLAlchemy only supplies enum/column types to the shared domain models (no database)."""
    assert "sqlalchemy" in requirement_names(BACKEND / "requirements-production.txt")
    document = (REPO / "docs" / "catalyst-runtime.md").read_text(encoding="utf-8")
    assert "SQLAlchemy" in document and "exception" in document.lower()


def test_backend_image_ships_no_migration_tooling_or_database_settings():
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "alembic" not in dockerfile.lower()
    assert not re.search(r"DATABASE_URL|PGSSL|POSTGRES|REDIS", dockerfile)


def test_no_application_module_imports_a_database_driver_or_redis():
    pattern = re.compile(r"^\s*(?:from|import)\s+(asyncpg|alembic|redis|psycopg2?|pg8000)\b", re.MULTILINE)
    offenders = [
        str(path.relative_to(BACKEND))
        for path in (BACKEND / "app").rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []


def test_compose_and_env_example_describe_postgresql_as_test_tooling_only():
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert not re.search(r"^\s*redis:|image:\s*redis", compose, re.MULTILINE | re.IGNORECASE)
    assert "TEST TOOLING ONLY" in compose
    env_example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    assert "BACKTEST_WORKER" not in env_example and "mode=worker" not in env_example.lower()
    assert "worker" not in re.sub(r"durable worker", "", env_example).lower()


PROBE = textwrap.dedent(
    """
    import importlib.abc, json, sys

    BLOCKED = {"asyncpg", "alembic", "redis", "psycopg", "psycopg2", "pg8000", "aiopg"}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ImportError(f"blocked: {name}")
            return None

    sys.meta_path.insert(0, Blocker())
    import asyncio
    from httpx import ASGITransport, AsyncClient
    import app.core.config as config

    # A developer's local .env must never influence (or be read by) this isolated probe.
    config.Settings.model_config["env_file"] = None
    import app.runtime as runtime

    async def main():
        async with AsyncClient(transport=ASGITransport(app=runtime.app), base_url="http://t") as client:
            live = (await client.get("/health/live")).status_code
            product = (await client.get("/api/v1/strategies")).status_code
        print(json.dumps({
            "live": live,
            "product": product,
            # The database session module is only imported by the configured application, and
            # even then it creates no engine for the Catalyst provider.
            "engine": getattr(sys.modules.get("app.db.session"), "engine", None) is None,
            "loaded": sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED),
        }))

    asyncio.run(main())
    """
)


def run_probe(**env: str) -> dict:
    clean = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "TEST_DATABASE_URL", "PERSISTENCE_PROVIDER", "APP_ENV"}
        and not key.startswith(("PGSSL", "X_ZOHO"))
    }
    clean.update(
        SECRET_KEY="a-long-unique-secret-for-the-isolated-runtime-probe",
        PYTHONDONTWRITEBYTECODE="1",
        **env,
    )
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=BACKEND,
        env=clean,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_catalyst_runtime_serves_with_postgresql_alembic_and_redis_unimportable():
    outcome = run_probe(
        APP_ENV="development",
        PERSISTENCE_PROVIDER="catalyst",
        # A stale connection string must be ignored, never used.
        DATABASE_URL="postgresql://stale:stale@example.invalid/legacy",
    )
    assert outcome["live"] == 200
    assert outcome["engine"] is True  # no database engine was ever created
    assert outcome["loaded"] == []
    assert outcome["product"] in (401, 403)  # the real app answered (auth), not the 503 stub


def test_catalyst_is_the_default_provider_outside_tests():
    outcome = run_probe(APP_ENV="development")
    assert outcome["engine"] is True and outcome["loaded"] == [] and outcome["product"] in (401, 403)


def test_production_refuses_to_fall_back_to_postgresql_and_exposes_no_routes():
    outcome = run_probe(
        APP_ENV="production",
        PERSISTENCE_PROVIDER="postgresql",
        DATABASE_URL="postgresql+asyncpg://stale:stale@example.invalid/legacy",
        FRONTEND_PUBLIC_URL="https://www.algoprofitx.com",
        API_PUBLIC_URL="https://api.algoprofitx.com",
        CORS_ALLOWED_ORIGINS="https://www.algoprofitx.com",
    )
    assert outcome["live"] == 200  # process stays observable
    assert outcome["product"] == 503  # but serves nothing and never opens a database
    assert outcome["engine"] is True and outcome["loaded"] == []


def test_a_catalyst_appsail_refuses_postgresql_in_any_environment():
    outcome = run_probe(
        APP_ENV="development",
        PERSISTENCE_PROVIDER="postgresql",
        DATABASE_URL="postgresql+asyncpg://stale:stale@example.invalid/legacy",
        X_ZOHO_CATALYST_LISTEN_PORT="9000",
    )
    assert outcome["product"] == 503 and outcome["engine"] is True and outcome["loaded"] == []
