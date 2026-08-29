from collections.abc import AsyncGenerator
from sqlalchemy.pool import NullPool

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


settings = get_settings()

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


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    """Close pooled connections during graceful application shutdown."""
    await engine.dispose()
