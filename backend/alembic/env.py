from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings
from app.db.base import Base
from app.models import (
    AllocationIntent,
    AllocationStatus,
    AuthSession,
    Backtest,
    BacktestStatus,
    ExecutionIntent,
    ExecutionStatus,
    Exchange,
    Instrument,
    InstrumentType,
    InstrumentVendorMapping,
    Role,
    Strategy,
    StrategyStatus,
    StrategyVersion,
    User,
    UserProfile,
)


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()

config.set_main_option(
    "sqlalchemy.url",
    # Alembic stores this value in ConfigParser, where percent signs trigger
    # interpolation. URL-encoded credentials therefore need literal escaping.
    settings.database_url.get_secret_value().replace("%", "%%"),
)

target_metadata = Base.metadata
MIGRATION_ADVISORY_LOCK_ID = 4_160_760_704_886_556_280


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    acquired = connection.execute(
        text("SELECT pg_try_advisory_lock(:lock_id)"),
        {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
    ).scalar_one()
    if not acquired:
        raise RuntimeError("Another AlgoProfitX migration runner owns the advisory lock")
    try:
        with context.begin_transaction():
            context.run_migrations()
    finally:
        connection.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
        )


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=settings.database_connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
