"""A small stateful Catalyst Data Store double for repository and service tests.

It understands the ZCQL shapes the repositories emit (``SELECT cols FROM t [WHERE a = 'x' [AND ...]]
[LIMIT n]``), enforces declared columns (a legacy table rejects an unknown column in SELECT and
INSERT, like the real Data Store) and unique columns, and can simulate an outage.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.persistence.catalyst import backtest as backtest_module
from app.persistence.catalyst import strategy as strategy_module
from app.persistence.catalyst.client import CatalystPersistenceError
from app.persistence.catalyst.schema import SCHEMA_VERSION_COLUMN


def columns_of(text: str) -> set[str]:
    return {column.strip() for column in text.split(",")}


def _unique_collision(rows: list[dict], payload: dict, unique: Iterable[str]) -> bool:
    return any(
        payload.get(key) is not None and any(row.get(key) == payload.get(key) for row in rows)
        for key in unique
    )


class MemoryDataStore:
    """``schemas`` maps table -> allowed columns (``None`` = permissive)."""

    def __init__(
        self,
        schemas: dict[str, set[str] | None],
        unique: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.schemas = schemas
        self.unique = unique or {}
        self.rows: dict[str, list[dict]] = {table: [] for table in schemas}
        self.counter = 0
        self.fail_all = False
        self.queries: list[str] = []

    # -- helpers -----------------------------------------------------------------------------
    def _check_columns(self, table: str, names: Iterable[str]) -> None:
        allowed = self.schemas.get(table)
        if allowed is None:
            return
        for name in names:
            if name != "ROWID" and name not in allowed:
                raise CatalystPersistenceError("Catalyst ZCQL query failed")

    # -- client surface ----------------------------------------------------------------------
    async def async_query_rows(self, query: str, table: str) -> list[dict]:
        self.queries.append(query)
        if self.fail_all:
            raise CatalystPersistenceError("Catalyst ZCQL query failed")
        match = re.match(r"SELECT (.+?) FROM (\w+)(?: WHERE (.+?))?(?: LIMIT (\d+))?$", query.strip())
        assert match, f"unsupported ZCQL in test double: {query}"
        selected = [column.strip() for column in match.group(1).split(",")]
        assert match.group(2) == table
        self._check_columns(table, selected)
        rows = list(self.rows[table])
        if match.group(3):
            for column, value in re.findall(r"(\w+) = '([^']*)'", match.group(3)):
                rows = [row for row in rows if row.get(column) == value]
        if match.group(4):
            rows = rows[: int(match.group(4))]
        return [{column: row.get(column) for column in selected} for row in rows]

    async def async_insert_row(self, table: str, payload: dict) -> dict:
        if self.fail_all:
            raise CatalystPersistenceError("Catalyst row insert failed")
        self._check_columns(table, payload)
        if _unique_collision(self.rows[table], payload, self.unique.get(table, ())):
            raise CatalystPersistenceError("Catalyst row insert failed")
        self.counter += 1
        row = {**payload, "ROWID": f"row-{self.counter}"}
        self.rows[table].append(row)
        return dict(row)

    async def async_update_row(self, table: str, payload: dict) -> dict:
        if self.fail_all:
            raise CatalystPersistenceError("Catalyst row update failed")
        self._check_columns(table, payload)
        row = next(item for item in self.rows[table] if item["ROWID"] == payload["ROWID"])
        row.update(payload)
        return dict(row)

    async def async_delete_row(self, table: str, row_id: str) -> None:
        if self.fail_all:
            raise CatalystPersistenceError("Catalyst row delete failed")
        self.rows[table] = [row for row in self.rows[table] if row["ROWID"] != row_id]


def strategy_store(*, with_schema_column: bool) -> MemoryDataStore:
    versions = columns_of(strategy_module._VERSION_COLUMNS)
    if with_schema_column:
        versions = versions | {SCHEMA_VERSION_COLUMN}
    return MemoryDataStore(
        {
            strategy_module.STRATEGIES_TABLE: columns_of(strategy_module._COLUMNS),
            strategy_module.STRATEGY_VERSIONS_TABLE: versions,
            strategy_module.STRATEGY_LOCKS_TABLE: columns_of(strategy_module._LOCK_COLUMNS),
        },
        {
            strategy_module.STRATEGIES_TABLE: ("strategy_uuid", "slug_lookup"),
            strategy_module.STRATEGY_VERSIONS_TABLE: ("version_uuid", "version_key"),
            strategy_module.STRATEGY_LOCKS_TABLE: ("strategy_uuid",),
        },
    )


def backtest_store(*, with_schema_column: bool) -> MemoryDataStore:
    backtests = columns_of(backtest_module._COLUMNS)
    if with_schema_column:
        backtests = backtests | {SCHEMA_VERSION_COLUMN}
    return MemoryDataStore(
        {
            backtest_module.BACKTESTS_TABLE: backtests,
            backtest_module.BACKTEST_CLAIMS_TABLE: None,
            backtest_module.BACKTEST_TERMINALS_TABLE: None,
        },
        {
            backtest_module.BACKTESTS_TABLE: ("backtest_uuid", "request_key"),
            backtest_module.BACKTEST_CLAIMS_TABLE: ("claim_key", "lease_token"),
            backtest_module.BACKTEST_TERMINALS_TABLE: ("backtest_uuid", "terminal_key"),
        },
    )
