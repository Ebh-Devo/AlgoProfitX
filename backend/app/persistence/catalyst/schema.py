"""Detect optional Catalyst Data Store columns without ever guessing.

Catalyst tables are provisioned by an operator, not by migrations, so a newer application can run
against a table that predates a column. ``definition_schema_version`` is the V1/V2 selector for
strategy versions and backtest snapshots. While the column is absent every stored row is a V1
definition (its meaning before the column existed), V1 behavior is unchanged, and writing a V2
definition is refused rather than stored as V1.
"""

from __future__ import annotations

import time
from typing import Any

from app.persistence.catalyst.client import CatalystPersistenceClient, CatalystPersistenceError


SCHEMA_VERSION_COLUMN = "definition_schema_version"
LEGACY_SCHEMA_VERSION = 1
SUPPORTED_WRITE_VERSIONS = frozenset({1, 2})
_PRESENT_TTL_SECONDS = 300.0
_ABSENT_TTL_SECONDS = 30.0


class SchemaVersionColumnUnavailable(CatalystPersistenceError):
    """The live table has no ``definition_schema_version`` column yet."""

    def __init__(self, table: str) -> None:
        super().__init__(
            f"Catalyst table {table} has no {SCHEMA_VERSION_COLUMN} column; "
            "Strategy V2 definitions cannot be stored until it is provisioned"
        )
        self.table = table


class SchemaCapabilities:
    """Process-local, short-lived cache of which optional columns a table has."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, tuple[bool, float]] = {}

    def clear(self) -> None:
        self._entries.clear()

    async def has_schema_version_column(
        self, client: CatalystPersistenceClient, table: str
    ) -> bool:
        now = self._clock()
        cached = self._entries.get(table)
        if cached is not None and cached[1] > now:
            return cached[0]
        present = await self._probe(client, table)
        ttl = _PRESENT_TTL_SECONDS if present else _ABSENT_TTL_SECONDS
        self._entries[table] = (present, now + ttl)
        return present

    @staticmethod
    async def _probe(client: CatalystPersistenceClient, table: str) -> bool:
        try:
            await client.async_query_rows(
                f"SELECT ROWID, {SCHEMA_VERSION_COLUMN} FROM {table} LIMIT 1", table
            )
            return True
        except CatalystPersistenceError:
            pass
        # The column query failed. Only conclude "missing" if the table itself is readable;
        # otherwise this is an outage and guessing would misread V2 rows as V1. Let it surface.
        await client.async_query_rows(f"SELECT ROWID FROM {table} LIMIT 1", table)
        return False


schema_capabilities = SchemaCapabilities()


def parse_schema_version(value: Any, label: str = "definition schema version") -> int:
    """A missing/blank value is a legacy V1 row; anything else must be a whole number.

    Unsupported numbers are passed through unchanged so they fail deterministically where they
    are used (execution loader), never silently as V1.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return LEGACY_SCHEMA_VERSION
    if isinstance(value, bool):
        raise CatalystPersistenceError(f"Catalyst row has invalid {label}")
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise CatalystPersistenceError(f"Catalyst row has invalid {label}") from exc
    if number < 1:
        raise CatalystPersistenceError(f"Catalyst row has invalid {label}")
    return number
