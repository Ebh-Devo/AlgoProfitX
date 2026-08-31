import asyncio

from sqlalchemy import text

from app.db.session import engine


async def database_ready(timeout_seconds: float) -> bool:
    async def check() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(check(), timeout=timeout_seconds)
    except Exception:
        return False
    return True
