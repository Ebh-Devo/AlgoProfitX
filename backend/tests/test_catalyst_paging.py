"""ZCQL result limits: 300 rows per SELECT (silently cut) and 20 explicit columns.

The double in ``catalyst_memory`` emulates the documented provider limits, so these tests prove that a
plain SELECT would truncate, that ``query_all`` pages through everything with keyset paging on ROWID,
and that anything it cannot return completely fails closed. Nothing touches a live Catalyst environment.
"""

import hashlib
import re
import uuid
from pathlib import Path

import pytest

from app.models.strategy import StrategyStatus
from app.persistence.catalyst import backtest as backtest_module
from app.persistence.catalyst import execution as execution_module
from app.persistence.catalyst.backtest import BACKTESTS_TABLE, CatalystBacktestRepository
from app.persistence.catalyst.client import CatalystPersistenceError
from app.persistence.catalyst.execution import EXECUTIONS_TABLE
from app.persistence.catalyst.paging import (
    DEFAULT_MAX_ROWS,
    PAGE_SIZE,
    ZCQL_MAX_EXPLICIT_COLUMNS,
    ZCQL_MAX_ROWS_PER_QUERY,
    CatalystResultTooLarge,
    query_all,
    select_list,
)
from app.persistence.catalyst.strategy import (
    STRATEGIES_TABLE,
    STRATEGY_VERSIONS_TABLE,
    CatalystStrategyRepository,
)
from app.schemas.backtest import BacktestCreateRequest
from tests.catalyst_e2e import full_store
from tests.catalyst_memory import MemoryDataStore
from tests.test_catalyst_backtest_repository import version as v1_backtest_version
from tests.test_catalyst_strategy_repository import CREATOR_ID, instrument, strategy_row

BASE_ROWID = 36851000001000000
CATALYST_DIR = Path(__file__).resolve().parents[1] / "app" / "persistence" / "catalyst"


def plain_store(table: str = "T", count: int = 0) -> MemoryDataStore:
    store = MemoryDataStore({table: None}, {})
    for index in range(count):
        store.rows[table].append({"ROWID": str(BASE_ROWID + index), "n": str(index), "g": "a" if index % 2 else "b"})
    return store


def rowids(rows):
    return [int(row["ROWID"]) for row in rows]


# ------------------------------------------------------------- the documented limits, emulated


@pytest.mark.asyncio
async def test_a_plain_select_is_silently_cut_at_the_documented_300_rows():
    store = plain_store(count=700)
    rows = await store.async_query_rows("SELECT ROWID, n FROM T", "T")
    assert len(rows) == ZCQL_MAX_ROWS_PER_QUERY == 300  # the hazard this module removes
    capped = await store.async_query_rows("SELECT ROWID, n FROM T LIMIT 1000", "T")
    assert len(capped) == 300  # even an explicit larger LIMIT is cut


@pytest.mark.asyncio
async def test_the_double_rejects_explicit_column_lists_over_the_documented_limit():
    store = plain_store(count=1)
    names = ", ".join(f"c{i}" for i in range(21))
    with pytest.raises(CatalystPersistenceError):
        await store.async_query_rows(f"SELECT {names} FROM T", "T")
    assert len(await store.async_query_rows("SELECT * FROM T", "T")) == 1


def test_select_list_switches_to_star_only_above_twenty_columns():
    twenty = ", ".join(f"c{i}" for i in range(ZCQL_MAX_EXPLICIT_COLUMNS))
    assert select_list(twenty) == twenty
    assert select_list(twenty + ", c20") == "*"
    assert PAGE_SIZE < ZCQL_MAX_ROWS_PER_QUERY


# ---------------------------------------------------------------------------------- query_all


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 249, 250, 251, 499, 500, 700, 1234])
async def test_query_all_returns_every_row_exactly_once_in_rowid_order(count):
    store = plain_store(count=count)
    rows = await query_all(store, "SELECT ROWID, n FROM T", "T")
    assert rowids(rows) == [BASE_ROWID + index for index in range(count)]


@pytest.mark.asyncio
async def test_query_all_pages_by_keyset_not_by_offset():
    store = plain_store(count=600)
    await query_all(store, "SELECT ROWID, n FROM T WHERE g = 'a'", "T")
    first, *rest = store.queries
    assert first == f"SELECT ROWID, n FROM T WHERE g = 'a' ORDER BY ROWID LIMIT {PAGE_SIZE}"
    assert all(re.search(r"AND ROWID > \d+ ORDER BY ROWID LIMIT 250$", query) for query in rest)
    assert not any("LIMIT" in query and "," in query.split("LIMIT")[1] for query in store.queries)  # no offsets


@pytest.mark.asyncio
async def test_query_all_applies_the_filter_to_every_page():
    store = plain_store(count=900)
    rows = await query_all(store, "SELECT ROWID, n, g FROM T WHERE g = 'a'", "T")
    assert len(rows) == 450 and {row["g"] for row in rows} == {"a"}


@pytest.mark.asyncio
async def test_query_all_without_a_where_clause_adds_one():
    store = plain_store(count=520)
    await query_all(store, "SELECT ROWID FROM T", "T")
    assert any(" WHERE ROWID > " in query for query in store.queries)


@pytest.mark.asyncio
async def test_an_or_condition_keeps_its_meaning_when_the_rowid_bound_is_added():
    seen = []

    class Recorder:
        async def async_query_rows(self, query, table):
            seen.append(query)
            if len(seen) == 1:
                return [{"ROWID": str(BASE_ROWID + i)} for i in range(PAGE_SIZE)]
            return []

    await query_all(Recorder(), "SELECT ROWID FROM T WHERE a = 'x' OR b = 'y'", "T")
    assert seen[1] == (
        f"SELECT ROWID FROM T WHERE (a = 'x' OR b = 'y') AND ROWID > {BASE_ROWID + PAGE_SIZE - 1} "
        f"ORDER BY ROWID LIMIT {PAGE_SIZE}"
    )


@pytest.mark.asyncio
async def test_exceeding_the_safety_bound_fails_closed_never_truncates():
    store = plain_store(count=700)
    with pytest.raises(CatalystResultTooLarge) as raised:
        await query_all(store, "SELECT ROWID, n FROM T", "T", max_rows=600)
    assert raised.value.max_rows == 600 and "T" in str(raised.value)
    # Exactly at the bound is fine; one over is not.
    assert len(await query_all(plain_store(count=600), "SELECT ROWID FROM T", "T", max_rows=600)) == 600
    with pytest.raises(CatalystResultTooLarge):
        await query_all(plain_store(count=601), "SELECT ROWID FROM T", "T", max_rows=600)
    assert DEFAULT_MAX_ROWS == 5000


@pytest.mark.asyncio
async def test_pages_that_cannot_be_continued_safely_are_an_error_not_a_partial_result():
    class StuckProvider:
        async def async_query_rows(self, query, table):  # always the same full page
            return [{"ROWID": str(BASE_ROWID + i)} for i in range(PAGE_SIZE)]

    with pytest.raises(CatalystPersistenceError, match="paged safely"):
        await query_all(StuckProvider(), "SELECT ROWID FROM T", "T")

    class NoRowid:
        async def async_query_rows(self, query, table):
            return [{"n": str(i)} for i in range(PAGE_SIZE)]

    with pytest.raises(CatalystPersistenceError, match="paged safely"):
        await query_all(NoRowid(), "SELECT n FROM T", "T")

    class Injected:
        async def async_query_rows(self, query, table):
            return [{"ROWID": "1; DROP TABLE x"} for _ in range(PAGE_SIZE)]

    with pytest.raises(CatalystPersistenceError, match="paged safely"):
        await query_all(Injected(), "SELECT ROWID FROM T", "T")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "SELECT ROWID FROM T LIMIT 5",
        "SELECT ROWID FROM T ORDER BY n",
        "SELECT ROWID FROM T GROUP BY n",
        "SELECT T.ROWID FROM T JOIN U ON T.a = U.a",
    ],
)
async def test_query_all_refuses_queries_it_cannot_page_safely(query):
    with pytest.raises(ValueError):
        await query_all(plain_store(count=1), query, "T")


# ------------------------------------------------------------ repositories over the 300-row cap


async def seed_strategies(store, total, *, published_every=1):
    for index in range(total):
        number = index + 1
        published = index % published_every == 0
        row = strategy_row(
            strategy_uuid=str(uuid.uuid4()),
            slug=f"s-{number}",
            slug_lookup=hashlib.sha256(f"s-{number}".encode("ascii")).hexdigest(),
            name=f"Strategy {number:04d}",
            status="published" if published else "draft",
            is_public=published,
            created_at=f"2026-09-09T06:{(number // 60) % 60:02d}:{number % 60:02d}+00:00",
            ROWID=str(BASE_ROWID + number),
            current_version_uuid=None,
        )
        store.rows[STRATEGIES_TABLE].append(row)


@pytest.mark.asyncio
async def test_marketplace_includes_every_discoverable_strategy_beyond_300_rows():
    store = full_store(with_schema_column=False)
    await seed_strategies(store, 900, published_every=2)  # 450 published, 450 drafts interleaved
    repository = CatalystStrategyRepository(store)
    everything = await repository.list_marketplace(limit=1000, offset=0)
    assert len(everything) == 450 and all(item.status is not StrategyStatus.DRAFT for item, _ in everything)
    page = await repository.list_marketplace(limit=100, offset=400)
    assert len(page) == 50  # the last page is real, not cut by the provider cap


@pytest.mark.asyncio
async def test_a_creators_strategy_list_is_complete_beyond_300_rows():
    store = full_store(with_schema_column=False)
    await seed_strategies(store, 320)
    for row in store.rows[STRATEGIES_TABLE]:
        row["creator_uuid"] = str(CREATOR_ID)
    listed = await CatalystStrategyRepository(store).list_strategies(CREATOR_ID)
    assert len(listed) == 320


@pytest.mark.asyncio
async def test_marketplace_fails_closed_when_the_catalog_exceeds_the_safety_bound():
    store = full_store(with_schema_column=False)
    await seed_strategies(store, DEFAULT_MAX_ROWS + 1)
    with pytest.raises(CatalystResultTooLarge):
        await CatalystStrategyRepository(store).list_marketplace(limit=10, offset=0)


@pytest.mark.asyncio
async def test_version_numbers_stay_correct_past_300_versions(provision_schema_version_column):
    store = full_store(with_schema_column=True)
    provision_schema_version_column()
    repository = CatalystStrategyRepository(store)
    strategy = await repository.create_strategy(
        creator_id=CREATOR_ID, name="Many Versions", slug="many-versions", description=None
    )
    for _ in range(302):
        created = await repository.create_version(
            strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
            configuration={"lookback": 20}, backtest_configuration={},
        )
    assert created.version_number == 302  # max()+1 over ALL rows, not over a 300-row cut
    versions = await repository.list_versions(strategy_id=strategy.id, creator_id=CREATOR_ID)
    assert [item.version_number for item in versions] == list(range(1, 303))
    assert len({row["version_key"] for row in store.rows[STRATEGY_VERSIONS_TABLE]}) == 302


@pytest.mark.asyncio
async def test_a_versions_backtest_list_is_complete_and_correctly_paged_beyond_300():
    store = full_store(with_schema_column=False)
    repository = CatalystBacktestRepository(store)
    version = v1_backtest_version()
    user = uuid.uuid4()
    for _ in range(310):
        await repository.create(version=version, requested_by_user_id=user, data=BacktestCreateRequest())
    everything = await repository.list(strategy_version_id=version.id, limit=1000, offset=0)
    assert len(everything) == 310
    last_page = await repository.list(strategy_version_id=version.id, limit=100, offset=300)
    assert len(last_page) == 10 and len({item.id for item in everything}) == 310


# ------------------------------------------------------------------ the 20-column limit


@pytest.mark.asyncio
async def test_wide_tables_are_read_with_select_star_never_over_twenty_explicit_columns():
    store = full_store(with_schema_column=True)
    repository = CatalystBacktestRepository(store)
    from app.persistence.catalyst.schema import schema_capabilities

    schema_capabilities._entries[BACKTESTS_TABLE] = (True, float("inf"))
    await repository.list(strategy_version_id=uuid.uuid4(), limit=10, offset=0)
    assert store.queries[-1].startswith(f"SELECT * FROM {BACKTESTS_TABLE} ")
    assert len(backtest_module._COLUMNS_WITH_SCHEMA.split(",")) > ZCQL_MAX_EXPLICIT_COLUMNS

    from app.persistence.catalyst.execution import CatalystExecutionRepository

    executions = CatalystExecutionRepository(store)
    await executions._rows(f"investor_uuid = '{uuid.uuid4()}'")
    assert store.queries[-1].startswith(f"SELECT * FROM {EXECUTIONS_TABLE} ")
    assert len(execution_module._COLUMNS.split(",")) > ZCQL_MAX_EXPLICIT_COLUMNS


@pytest.mark.asyncio
async def test_a_bounded_execution_lookup_is_not_paged():
    store = full_store(with_schema_column=False)
    from app.persistence.catalyst.execution import CatalystExecutionRepository

    await CatalystExecutionRepository(store)._rows("idempotency_lookup = 'ab' LIMIT 1")
    assert "ORDER BY" not in store.queries[-1] and store.queries[-1].endswith("LIMIT 1")


# ---------------------------------------------------------------------- static guards


def _query_call_sites():
    for path in sorted(CATALYST_DIR.glob("*.py")):
        if path.name in {"client.py", "schema.py", "paging.py", "__init__.py"}:
            continue
        lines = path.read_text(encoding="utf-8").split("\n")
        for number, line in enumerate(lines):
            if "async_query_rows(" in line and "def " not in line:
                block = "\n".join(lines[number : number + 9])
                snippet = block.split("\n        )")[0]
                function = re.findall(r"\n    (?:async )?def (\w+)", "\n".join(lines[:number]))[-1]
                yield path.name, function, "LIMIT" in snippet


# Direct reads that are bounded by construction: the LIMIT lives in the caller's query text.
ALLOWED_WITHOUT_LIMIT_IN_CALL = {("identity.py", "_one_or_none")}


def test_every_direct_select_is_a_limited_lookup_and_every_list_goes_through_query_all():
    offenders = [
        f"{name}:{function}"
        for name, function, has_limit in _query_call_sites()
        if not has_limit and (name, function) not in ALLOWED_WITHOUT_LIMIT_IN_CALL
    ]
    assert offenders == [], "unbounded async_query_rows calls (use query_all): " + ", ".join(offenders)
    # The guard itself finds the call sites it is meant to police.
    assert sum(1 for _ in _query_call_sites()) >= 15


def test_identity_lookups_are_limited_in_their_query_text():
    source = (CATALYST_DIR / "identity.py").read_text(encoding="utf-8")
    assert source.count("LIMIT 1") >= 3
