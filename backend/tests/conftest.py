import os
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from dotenv import dotenv_values
from sqlalchemy import insert, text
from sqlalchemy.engine import make_url


BACKEND_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"

# Route persistence is selected by environment. Tests must never inherit the
# application's Development default and accidentally contact Catalyst.
os.environ["APP_ENV"] = "test"

# Make local runs reproduce CI: a developer's git-ignored backend/.env must never change the
# settings the tests see. CI supplies only DATABASE_URL/TEST_DATABASE_URL and SECRET_KEY (below);
# TEST_DATABASE_URL is still read from .env on purpose by _require_test_database().
os.environ.setdefault("SECRET_KEY", "ci-only-secret-not-for-production")
from app.core.config import Settings  # noqa: E402

Settings.model_config["env_file"] = None


def _require_test_database() -> str:
    # Direct pytest invocations from CMD do not run the PowerShell environment
    # loader. Read only TEST_DATABASE_URL from the same local .env file used by
    # application settings, while still refusing to fall back to DATABASE_URL.
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url and BACKEND_ENV_FILE.is_file():
        configured = dotenv_values(BACKEND_ENV_FILE).get("TEST_DATABASE_URL")
        database_url = configured if isinstance(configured, str) else None

    if not database_url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set before running tests. "
            "Refusing to use DATABASE_URL."
        )

    if make_url(database_url).database != "tradeebh_test":
        raise RuntimeError(
            "TEST_DATABASE_URL must target the tradeebh_test database."
        )

    return database_url


# This runs before test modules import app.db.session, ensuring every test
# session and API request uses the dedicated test database.
os.environ["DATABASE_URL"] = _require_test_database()

from app.db.session import engine  # noqa: E402
from app.core.abuse import abuse_controller  # noqa: E402
from app.models.user import Role  # noqa: E402


ROLE_NAMES = ("ADMIN", "CREATOR", "INVESTOR")


async def _reset_database() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE auth_sessions, instrument_vendor_mappings, instruments, exchanges, user_roles, user_profiles, "
                "execution_intents, allocation_intents, backtests, strategy_versions, strategies, users, roles CASCADE"
            )
        )
        await connection.execute(
            insert(Role),
            [{"id": uuid.uuid4(), "name": name} for name in ROLE_NAMES],
        )


# Modules that never use PostgreSQL (Catalyst doubles, proxy and static checks). They run without
# touching any database at all, which also proves they do not depend on one.
DATABASE_FREE_MODULES = frozenset(
    {
        "test_web_proxy.py",
        "test_workflow_environment_isolation.py",
        "test_catalyst_only_runtime.py",
    }
)


def _is_database_free(request) -> bool:
    name = request.path.name
    return name.startswith("test_catalyst_") or name in DATABASE_FREE_MODULES


@pytest.fixture(autouse=True)
def catalyst_schema_capabilities():
    """Default every test to the legacy table layout (no definition_schema_version column).

    The capability probe is process-global; tests that exercise V2 storage opt in explicitly with
    ``provision_schema_version_column``.
    """
    from app.persistence.catalyst.backtest import BACKTESTS_TABLE
    from app.persistence.catalyst.schema import schema_capabilities
    from app.persistence.catalyst.strategy import STRATEGY_VERSIONS_TABLE

    schema_capabilities.clear()
    for table in (STRATEGY_VERSIONS_TABLE, BACKTESTS_TABLE):
        schema_capabilities._entries[table] = (False, float("inf"))
    yield
    schema_capabilities.clear()


@pytest.fixture
def provision_schema_version_column():
    """Declare the optional column present for the tables a test touches."""
    from app.persistence.catalyst.backtest import BACKTESTS_TABLE
    from app.persistence.catalyst.schema import schema_capabilities
    from app.persistence.catalyst.strategy import STRATEGY_VERSIONS_TABLE

    def provision() -> None:
        for table in (STRATEGY_VERSIONS_TABLE, BACKTESTS_TABLE):
            schema_capabilities._entries[table] = (True, float("inf"))

    return provision


@pytest_asyncio.fixture(autouse=True)
async def reset_test_database(request):
    """Keep committed API requests isolated without touching development data."""
    if _is_database_free(request):
        await abuse_controller.clear()
        yield
        await abuse_controller.clear()
        return
    await abuse_controller.clear()
    await _reset_database()
    if request.path.name != "test_instruments.py":
        from app.bootstrap.instruments import bootstrap_market_foundation
        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            await bootstrap_market_foundation(session)
    yield
    await abuse_controller.clear()
    await _reset_database()
