"""Safe multi-row reads from Catalyst Data Store / ZCQL.

Documented provider limits (Catalyst Docs: ZCQL "General Syntax of SELECT" and the Cloud Scale FAQ):

* a ZCQL ``SELECT`` returns **at most 300 rows** (the FAQ is literally "Why do I get only 300 rows ...?");
  the docs do not say whether an over-limit result is an error or silently cut, so it must be assumed cut;
* an explicit column list is limited to **20 columns** ("a maximum of 20 columns"); ``SELECT *`` has no
  stated column limit;
* more rows are fetched by iterating with the ``LIMIT [offset,]count`` clause. The docs are not fully
  consistent about whether ``offset`` is 0- or 1-based, so this module does **not** use offsets.

``query_all`` therefore pages by **keyset** on ``ROWID`` (``WHERE ... AND ROWID > <last> ORDER BY ROWID
LIMIT <page>``), which needs no offset semantics, and **fails closed**: if a result would exceed
``max_rows`` it raises ``CatalystResultTooLarge`` instead of returning a truncated list.
"""

from __future__ import annotations

import re
from typing import Any

from app.persistence.catalyst.client import CatalystPersistenceClient, CatalystPersistenceError


ZCQL_MAX_ROWS_PER_QUERY = 300
ZCQL_MAX_EXPLICIT_COLUMNS = 20
PAGE_SIZE = 250  # strictly below the documented per-query cap
DEFAULT_MAX_ROWS = 5000
_ROWID = re.compile(r"^[0-9]{1,24}$")


class CatalystResultTooLarge(CatalystPersistenceError):
    """A multi-row read exceeded its safety bound; returning it truncated would be wrong."""

    def __init__(self, table: str, max_rows: int) -> None:
        super().__init__(f"Catalyst result for {table} exceeds the {max_rows}-row safety bound")
        self.table = table
        self.max_rows = max_rows


def select_list(columns: str) -> str:
    """``columns`` as written, or ``*`` when the list is longer than ZCQL's explicit-column limit."""
    names = [name.strip() for name in columns.split(",") if name.strip()]
    return "*" if len(names) > ZCQL_MAX_EXPLICIT_COLUMNS else ", ".join(names)


async def query_all(
    client: CatalystPersistenceClient,
    query: str,
    table: str,
    *,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> list[dict[str, Any]]:
    """Every row matching ``query`` (a plain ``SELECT ... [WHERE ...]``), never silently truncated."""
    upper = query.upper()
    if " LIMIT " in f" {upper} " or " ORDER BY " in upper:
        raise ValueError("query_all builds its own ORDER BY and LIMIT")
    if " GROUP BY " in upper or " JOIN " in upper:
        raise ValueError("query_all supports only plain single-table selects")
    head, separator, condition = query.partition(" WHERE ")
    if separator and " OR " in condition.upper():
        condition = f"({condition})"  # keep the original meaning once ROWID is ANDed on

    def after(last: int) -> str:
        return f"{head} WHERE {condition} AND ROWID > {last}" if separator else f"{head} WHERE ROWID > {last}"

    rows: list[dict[str, Any]] = []
    last_rowid: int | None = None
    while True:
        paged = query if last_rowid is None else after(last_rowid)
        page = await client.async_query_rows(f"{paged} ORDER BY ROWID LIMIT {PAGE_SIZE}", table)
        rows.extend(page)
        if len(rows) > max_rows:
            raise CatalystResultTooLarge(table, max_rows)
        if len(page) < PAGE_SIZE:
            return rows
        # A full page: continue after its last ROWID (validated, never interpolated blindly).
        candidate = str(page[-1].get("ROWID", ""))
        if not _ROWID.fullmatch(candidate) or (last_rowid is not None and int(candidate) <= last_rowid):
            raise CatalystPersistenceError("Catalyst returned rows that cannot be paged safely")
        last_rowid = int(candidate)
