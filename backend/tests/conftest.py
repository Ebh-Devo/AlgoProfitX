import os
import uuid

import pytest_asyncio
from sqlalchemy import insert, text
from sqlalchemy.engine import make_url


def _require_test_database() -> str:
    database_url = os.environ.get("TEST_DATABASE_URL")

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
from app.models.user import Role  # noqa: E402


ROLE_NAMES = ("ADMIN", "CREATOR", "INVESTOR")


async def _reset_database() -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE user_roles, user_profiles, execution_intents, allocation_intents, backtests, strategy_versions, "
                "strategies, users, roles CASCADE"
            )
        )
        await connection.execute(
            insert(Role),
            [{"id": uuid.uuid4(), "name": name} for name in ROLE_NAMES],
        )


@pytest_asyncio.fixture(autouse=True)
async def reset_test_database():
    """Keep committed API requests isolated without touching development data."""
    await _reset_database()
    yield
    await _reset_database()
