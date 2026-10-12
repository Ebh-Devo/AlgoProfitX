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
        self.row_cap = 300  # documented: a ZCQL SELECT returns at most 300 rows
        self.max_explicit_columns = 20  # documented: at most 20 explicit columns

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
        """ZCQL as documented by Catalyst and observed in the Development console: at most ``row_cap`` rows
        (silently cut without a LIMIT, assumed), ``LIMIT`` above 300 rejected, 1-based offsets, ``SELECT *``,
        ``ORDER BY``. The documented 20-explicit-column limit is NOT enforced live (21 and 29 columns were
        accepted), but the double still rejects it so the code stays compliant with the documentation."""
        self.queries.append(query)
        if self.fail_all:
            raise CatalystPersistenceError("Catalyst ZCQL query failed")
        match = re.match(
            r"SELECT (.+?) FROM (\w+)(?: WHERE (.+?))?(?: ORDER BY (\w+))?(?: LIMIT (\d+)(?:,(\d+))?)?$",
            query.strip(),
        )
        assert match, f"unsupported ZCQL in test double: {query}"
        assert match.group(2) == table
        columns, where, order_by, first, second = (match.group(n) for n in (1, 3, 4, 5, 6))
        select_all = columns.strip() == "*"
        selected = [] if select_all else [column.strip() for column in columns.split(",")]
        if len(selected) > self.max_explicit_columns:
            raise CatalystPersistenceError("Catalyst ZCQL query failed")  # documented 20-column limit
        self._check_columns(table, selected)
        rows = list(self.rows[table])
        if where:
            for column, value in re.findall(r"(\w+) = '([^']*)'", where):
                rows = [row for row in rows if row.get(column) == value]
            for bound in re.findall(r"ROWID > (\d+)", where):
                rows = [row for row in rows if int(row["ROWID"]) > int(bound)]
        if order_by:
            assert order_by == "ROWID", "the double only orders by ROWID"
            rows.sort(key=lambda row: int(row["ROWID"]))
        # Observed live (Development ZCQL Console, 2026-10-10): ``LIMIT offset,count`` offsets are
        # 1-based (0 behaves like 1) and a LIMIT above 300 is an error, not a silent cut.
        offset, count = (int(first), int(second)) if second is not None else (1, int(first) if first else None)
        if count is not None and count > self.row_cap:
            raise CatalystPersistenceError("ZCQL CANNOT HAVE MORE THAN 300 ROWS in LIMIT")
        rows = rows[max(offset, 1) - 1 :]
        # Without a LIMIT the documented 300-row cap applies; whether that is a silent cut or an error
        # has NOT been observed live (it needs more than 300 rows), so it is assumed silent (worst case).
        rows = rows[: self.row_cap if count is None else count]
        if select_all:
            keys = self.schemas.get(table) or None
            return [
                {**{key: row.get(key) for key in (keys or row)}, "ROWID": row["ROWID"]} for row in rows
            ]
        return [{column: row.get(column) for column in selected} for row in rows]

    async def async_insert_row(self, table: str, payload: dict) -> dict:
        if self.fail_all:
            raise CatalystPersistenceError("Catalyst row insert failed")
        self._check_columns(table, payload)
        if _unique_collision(self.rows[table], payload, self.unique.get(table, ())):
            raise CatalystPersistenceError("Catalyst row insert failed")
        self.counter += 1
        row = {**payload, "ROWID": str(36851000000000000 + self.counter)}  # real ROWIDs are numeric
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
