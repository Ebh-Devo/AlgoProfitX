import asyncio
from urllib.parse import unquote, urlsplit

from app.core.config import get_settings
from app.db import session as database_session
from sqlalchemy import text


async def database_ready(timeout_seconds: float) -> bool:
    async def check() -> None:
        settings = get_settings()
        if settings.database_url is None:
            raise RuntimeError("Database configuration is unavailable")
        database_url = urlsplit(settings.database_url.get_secret_value())
        expected_database = database_url.path.lstrip("/").split("/", 1)[0]
        expected_user = unquote(database_url.username or "")
        database_session._initialize_database()
        if database_session.engine is None:
            raise RuntimeError("Database engine is unavailable")
        async with database_session.engine.connect() as connection:
            result = await connection.execute(
                text(
                    "SELECT current_database(), current_user, "
                    "(SELECT version_num FROM alembic_version LIMIT 1)"
                )
            )
            database, user, revision = result.one()
            if database != expected_database or user != expected_user:
                raise RuntimeError("Database identity does not match runtime configuration")
            if revision != settings.readiness_alembic_head:
                raise RuntimeError("Database schema is not at the configured Alembic head")
            privilege_result = await connection.execute(
                text(
                    "SELECT coalesce(bool_and("
                    "has_table_privilege(current_user, "
                    "format('%I.%I', namespaces.nspname, classes.relname), 'SELECT') "
                    "AND has_table_privilege(current_user, "
                    "format('%I.%I', namespaces.nspname, classes.relname), 'INSERT') "
                    "AND has_table_privilege(current_user, "
                    "format('%I.%I', namespaces.nspname, classes.relname), 'UPDATE') "
                    "AND has_table_privilege(current_user, "
                    "format('%I.%I', namespaces.nspname, classes.relname), 'DELETE')"
                    "), true) "
                    "FROM pg_catalog.pg_class AS classes "
                    "JOIN pg_catalog.pg_namespace AS namespaces "
                    "ON namespaces.oid = classes.relnamespace "
                    "WHERE namespaces.nspname = 'public' "
                    "AND classes.relkind IN ('r', 'p') "
                    "AND classes.relname <> 'alembic_version'"
                )
            )
            if not privilege_result.scalar_one():
                raise RuntimeError("Runtime database account lacks application table privileges")

    await asyncio.wait_for(check(), timeout=timeout_seconds)
    return True
