from collections.abc import AsyncGenerator
from sqlalchemy.pool import NullPool

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


settings = get_settings()
engine = None
AsyncSessionLocal = None


def _initialize_database():
    global engine, AsyncSessionLocal
    if settings.uses_catalyst_persistence:
        return None
    if engine is None:
        assert settings.database_url is not None
        engine = create_async_engine(
            settings.database_url.get_secret_value(),
            **settings.database_engine_options,
            **({} if settings.uses_application_pool else {"poolclass": NullPool}),
        )
        AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return AsyncSessionLocal


# Preserve the module-level engine and session factory used by the legacy
# PostgreSQL runtime and its migration-backed test suite. Catalyst runtimes
# return before importing a database driver or creating an engine.
_initialize_database()


async def get_session() -> AsyncGenerator[AsyncSession | None, None]:
    factory = _initialize_database()
    if factory is None:
        yield None
        return
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Close pooled connections during graceful application shutdown."""
    if engine is not None:
        await engine.dispose()
