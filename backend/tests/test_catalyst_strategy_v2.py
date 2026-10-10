"""Strategy V2 on Catalyst-native persistence: storage, schema-version safety, gating, execution.

All tests run against in-memory Data Store doubles; nothing touches a live Catalyst environment.
"""

import dataclasses
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import strategies as routes
from app.models.backtest import BacktestStatus
from app.models.strategy import StrategyStatus
from app.persistence.catalyst.allocation import (
    ALLOCATIONS_TABLE,
    CatalystAllocationEligibilityError,
    CatalystAllocationRepository,
)
from app.persistence.catalyst.backtest import BACKTESTS_TABLE, CatalystBacktestRepository
from app.persistence.catalyst.client import CatalystPersistenceError
from app.persistence.catalyst.schema import (
    SCHEMA_VERSION_COLUMN,
    SchemaCapabilities,
    SchemaVersionColumnUnavailable,
    parse_schema_version,
    schema_capabilities,
)
from app.persistence.catalyst.strategy import (
    STRATEGIES_TABLE,
    STRATEGY_LOCKS_TABLE,
    STRATEGY_VERSIONS_TABLE,
    CatalystStrategyRepository,
)
from app.schemas.backtest import BacktestCreateRequest
from app.schemas.strategy import StrategyVersionCreateRequest, StrategyVersionV2CreateRequest
from app.services.catalyst_backtest import execute_catalyst_backtest
from app.services.strategy import UnsupportedExecutionVersionError
from app.strategy_definition.schema import CrossCondition, SharesSizing
from tests.catalyst_memory import MemoryDataStore, backtest_store, strategy_store
from tests.strategy_v2_builders import D, ind, leg, long_definition, op, position, rule
from tests.test_catalyst_backtest_repository import version as v1_backtest_version
from tests.test_catalyst_strategy_repository import CREATOR_ID, instrument

V2_ENV = {
    "initial_capital": "10000",
    "fill_model": "same_bar_close",
    "timeframe": "1d",
    "start_date": "2025-01-01T00:00:00Z",
}


def v2_document(fast: int = 3, slow: int = 5) -> dict:
    return long_definition(
        positions=(position(legs=[leg()], sizing=SharesSizing(D(5))),),
        rules=(
            rule("enter", CrossCondition("above", ind("ema", fast, "1d"), ind("ema", slow, "1d")), [op("open")]),
            rule("exit", CrossCondition("below", ind("ema", fast, "1d"), ind("ema", slow, "1d")), [op("close")]),
        ),
    ).to_dict()


V1_CONFIG = {"lookback": 20}


async def new_strategy(repository: CatalystStrategyRepository, slug: str = "momentum-strategy"):
    return await repository.create_strategy(
        creator_id=CREATOR_ID, name="Momentum Strategy", slug=slug, description=None
    )


# ---------------------------------------------------------------------- capability detection


@pytest.mark.asyncio
async def test_probe_reports_present_absent_and_never_guesses_during_an_outage():
    schema_capabilities.clear()
    with_column = strategy_store(with_schema_column=True)
    assert await schema_capabilities.has_schema_version_column(with_column, STRATEGY_VERSIONS_TABLE) is True

    schema_capabilities.clear()
    legacy = strategy_store(with_schema_column=False)
    assert await schema_capabilities.has_schema_version_column(legacy, STRATEGY_VERSIONS_TABLE) is False

    # An outage is not evidence that the column is missing: surface it, never cache "absent".
    schema_capabilities.clear()
    legacy.fail_all = True
    with pytest.raises(CatalystPersistenceError):
        await schema_capabilities.has_schema_version_column(legacy, STRATEGY_VERSIONS_TABLE)
    assert STRATEGY_VERSIONS_TABLE not in schema_capabilities._entries


@pytest.mark.asyncio
async def test_probe_results_are_cached_and_absence_expires_quickly():
    now = [1000.0]
    capabilities = SchemaCapabilities(clock=lambda: now[0])
    store = strategy_store(with_schema_column=False)
    assert await capabilities.has_schema_version_column(store, STRATEGY_VERSIONS_TABLE) is False
    calls = len(store.queries)
    assert await capabilities.has_schema_version_column(store, STRATEGY_VERSIONS_TABLE) is False
    assert len(store.queries) == calls  # served from cache

    # The operator provisions the column; the application notices without a restart.
    store.schemas[STRATEGY_VERSIONS_TABLE] = store.schemas[STRATEGY_VERSIONS_TABLE] | {SCHEMA_VERSION_COLUMN}
    now[0] += 31
    assert await capabilities.has_schema_version_column(store, STRATEGY_VERSIONS_TABLE) is True


def test_schema_version_parsing_defaults_to_v1_and_never_coerces_garbage():
    assert parse_schema_version(None) == 1
    assert parse_schema_version("") == 1
    assert parse_schema_version("  ") == 1
    assert parse_schema_version(1) == 1
    assert parse_schema_version("2") == 2
    assert parse_schema_version(3) == 3  # unsupported values pass through to fail at execution
    for bad in ("abc", "0", -1, True, "1.5"):
        with pytest.raises(CatalystPersistenceError):
            parse_schema_version(bad)


# ------------------------------------------------------------------------- strategy versions


@pytest.mark.asyncio
async def test_legacy_table_keeps_v1_working_and_refuses_to_store_v2(provision_schema_version_column):
    store = strategy_store(with_schema_column=False)
    repository = CatalystStrategyRepository(store)
    strategy = await new_strategy(repository)

    v1 = await repository.create_version(
        strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
        configuration=V1_CONFIG, backtest_configuration={},
    )
    assert v1.definition_schema_version == 1
    stored = store.rows[STRATEGY_VERSIONS_TABLE][0]
    assert SCHEMA_VERSION_COLUMN not in stored  # the legacy payload is unchanged

    with pytest.raises(SchemaVersionColumnUnavailable):
        await repository.create_version(
            strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
            configuration=v2_document(), backtest_configuration=V2_ENV, definition_schema_version=2,
        )
    assert len(store.rows[STRATEGY_VERSIONS_TABLE]) == 1  # nothing stored, never as V1
    assert store.rows[STRATEGY_LOCKS_TABLE] == []  # no lock left behind
    listed = await repository.list_versions(strategy_id=strategy.id, creator_id=CREATOR_ID)
    assert [item.definition_schema_version for item in listed] == [1]


@pytest.mark.asyncio
async def test_provisioned_table_round_trips_both_versions_and_legacy_rows(provision_schema_version_column):
    store = strategy_store(with_schema_column=True)
    provision_schema_version_column()
    repository = CatalystStrategyRepository(store)
    strategy = await new_strategy(repository)

    v1 = await repository.create_version(
        strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
        configuration=V1_CONFIG, backtest_configuration={},
    )
    v2 = await repository.create_version(
        strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
        configuration=v2_document(), backtest_configuration=V2_ENV, definition_schema_version=2,
    )
    assert (v1.definition_schema_version, v2.definition_schema_version) == (1, 2)
    assert (v1.version_number, v2.version_number) == (1, 2)
    assert [row[SCHEMA_VERSION_COLUMN] for row in store.rows[STRATEGY_VERSIONS_TABLE]] == [1, 2]

    # A row written before the column existed has no value: it is a V1 definition.
    store.rows[STRATEGY_VERSIONS_TABLE][0].pop(SCHEMA_VERSION_COLUMN)
    fetched = await repository.get_version(
        strategy_id=strategy.id, version_id=v1.id, creator_id=CREATOR_ID
    )
    assert fetched is not None and fetched.definition_schema_version == 1
    again = await repository.get_version(
        strategy_id=strategy.id, version_id=v2.id, creator_id=CREATOR_ID
    )
    assert again is not None and again.definition_schema_version == 2
    assert again.configuration == v2_document()


@pytest.mark.asyncio
async def test_only_known_write_versions_are_accepted(provision_schema_version_column):
    store = strategy_store(with_schema_column=True)
    provision_schema_version_column()
    repository = CatalystStrategyRepository(store)
    strategy = await new_strategy(repository)
    for bad in (0, 3, -1):
        with pytest.raises(ValueError, match="Unsupported strategy definition schema version"):
            await repository.create_version(
                strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
                configuration=V1_CONFIG, backtest_configuration={}, definition_schema_version=bad,
            )
    assert store.rows[STRATEGY_VERSIONS_TABLE] == []


@pytest.mark.asyncio
async def test_oversized_definition_is_rejected_before_any_write(provision_schema_version_column):
    store = strategy_store(with_schema_column=True)
    provision_schema_version_column()
    repository = CatalystStrategyRepository(store)
    strategy = await new_strategy(repository)
    huge = v2_document()
    huge["padding"] = "x" * 20000
    with pytest.raises(ValueError, match="too large"):
        await repository.create_version(
            strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
            configuration=huge, backtest_configuration=V2_ENV, definition_schema_version=2,
        )
    assert store.rows[STRATEGY_VERSIONS_TABLE] == []
    assert store.rows[STRATEGY_LOCKS_TABLE] == []


@pytest.mark.asyncio
async def test_outage_during_a_version_read_fails_instead_of_reading_v2_as_v1():
    schema_capabilities.clear()  # use the real probe
    store = strategy_store(with_schema_column=True)
    repository = CatalystStrategyRepository(store)
    strategy_id = uuid.uuid4()
    store.fail_all = True
    with pytest.raises(CatalystPersistenceError):
        await repository.list_versions(strategy_id=strategy_id, creator_id=CREATOR_ID)


# ------------------------------------------------------------------- lifecycle and allocation


async def seeded_strategy(store: MemoryDataStore, *, version_schema: int):
    repository = CatalystStrategyRepository(store)
    strategy = await new_strategy(repository)
    version = await repository.create_version(
        strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
        configuration=v2_document() if version_schema == 2 else V1_CONFIG,
        backtest_configuration=V2_ENV if version_schema == 2 else {},
        definition_schema_version=version_schema,
    )
    return repository, strategy, version


@pytest.mark.asyncio
async def test_v2_versions_cannot_be_published_or_deployed(provision_schema_version_column):
    store = strategy_store(with_schema_column=True)
    provision_schema_version_column()
    repository, strategy, _ = await seeded_strategy(store, version_schema=2)
    with pytest.raises(UnsupportedExecutionVersionError) as raised:
        await repository.transition_strategy(
            strategy_id=strategy.id, creator_id=CREATOR_ID, target=StrategyStatus.PUBLISHED
        )
    assert raised.value.detail()["code"] == "strategy_definition_version_unsupported_for_execution"
    row = store.rows[STRATEGIES_TABLE][0]
    assert row["status"] == "draft" and not row["is_public"]  # nothing was changed

    # A V1 strategy publishes; if its pinned current version is somehow V2, deploy is refused too.
    v1_repo, v1_strategy, _ = await seeded_strategy(strategy_store(with_schema_column=True), version_schema=1)
    published = await v1_repo.transition_strategy(
        strategy_id=v1_strategy.id, creator_id=CREATOR_ID, target=StrategyStatus.PUBLISHED
    )
    assert published is not None and published.status is StrategyStatus.PUBLISHED
    deployed = await v1_repo.transition_strategy(
        strategy_id=v1_strategy.id, creator_id=CREATOR_ID, target=StrategyStatus.DEPLOYED
    )
    assert deployed is not None and deployed.status is StrategyStatus.DEPLOYED


@pytest.mark.asyncio
async def test_deploy_is_refused_when_the_pinned_version_is_v2(provision_schema_version_column):
    store = strategy_store(with_schema_column=True)
    provision_schema_version_column()
    repository, strategy, v1 = await seeded_strategy(store, version_schema=1)
    v2 = await repository.create_version(
        strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
        configuration=v2_document(), backtest_configuration=V2_ENV, definition_schema_version=2,
    )
    row = store.rows[STRATEGIES_TABLE][0]
    row.update(status="published", is_public=True, current_version_uuid=str(v2.id))
    with pytest.raises(UnsupportedExecutionVersionError):
        await repository.transition_strategy(
            strategy_id=strategy.id, creator_id=CREATOR_ID, target=StrategyStatus.DEPLOYED
        )
    assert row["status"] == "published"


@pytest.mark.asyncio
async def test_allocation_requires_a_v1_version(provision_schema_version_column):
    store = strategy_store(with_schema_column=True)
    store.schemas[ALLOCATIONS_TABLE] = None
    store.rows[ALLOCATIONS_TABLE] = []
    provision_schema_version_column()
    repository, strategy, v1 = await seeded_strategy(store, version_schema=1)
    v2 = await repository.create_version(
        strategy_id=strategy.id, creator_id=CREATOR_ID, instrument=instrument(),
        configuration=v2_document(), backtest_configuration=V2_ENV, definition_schema_version=2,
    )
    allocations = CatalystAllocationRepository(store)
    row = store.rows[STRATEGIES_TABLE][0]
    row.update(status="deployed", is_public=True, current_version_uuid=str(v2.id))

    with pytest.raises(UnsupportedExecutionVersionError):
        await allocations.create(
            investor_user_id=uuid.uuid4(), strategy_id=strategy.id,
            notional_amount=Decimal("1000"), currency="INR",
        )
    assert store.rows[ALLOCATIONS_TABLE] == []

    row["current_version_uuid"] = str(v1.id)
    created = await allocations.create(
        investor_user_id=uuid.uuid4(), strategy_id=strategy.id,
        notional_amount=Decimal("1000"), currency="INR",
    )
    assert created.strategy_version_id == v1.id
    assert issubclass(CatalystAllocationEligibilityError, Exception)


# -------------------------------------------------------------------------------- backtests


def v2_backtest_version(schema: int = 2):
    return dataclasses.replace(
        v1_backtest_version(),
        configuration=v2_document(), backtest_configuration=V2_ENV, definition_schema_version=schema,
    )


@pytest.mark.asyncio
async def test_backtest_snapshots_the_schema_version_when_provisioned(provision_schema_version_column):
    store = backtest_store(with_schema_column=True)
    provision_schema_version_column()
    repository = CatalystBacktestRepository(store)
    v1 = await repository.create(
        version=v1_backtest_version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    v2 = await repository.create(
        version=v2_backtest_version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    assert (v1.definition_schema_version, v2.definition_schema_version) == (1, 2)
    fetched = await repository.get(strategy_version_id=v2.strategy_version_id, backtest_id=v2.id)
    assert fetched is not None and fetched.definition_schema_version == 2


@pytest.mark.asyncio
async def test_legacy_backtest_table_reads_v1_and_refuses_a_v2_snapshot():
    store = backtest_store(with_schema_column=False)
    repository = CatalystBacktestRepository(store)
    v1 = await repository.create(
        version=v1_backtest_version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    assert v1.definition_schema_version == 1
    assert SCHEMA_VERSION_COLUMN not in store.rows[BACKTESTS_TABLE][0]
    with pytest.raises(SchemaVersionColumnUnavailable):
        await repository.create(
            version=v2_backtest_version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
        )
    assert len(store.rows[BACKTESTS_TABLE]) == 1


async def run_backtest(version, provision):
    store = backtest_store(with_schema_column=True)
    provision()
    repository = CatalystBacktestRepository(store)
    queued = await repository.create(
        version=version, requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    return repository, store, queued, await execute_catalyst_backtest(repository, queued.id)


@pytest.mark.asyncio
async def test_v2_backtest_runs_on_the_strategy_runtime_and_persists_a_terminal_result(
    provision_schema_version_column,
):
    repository, store, queued, completed = await run_backtest(
        v2_backtest_version(), provision_schema_version_column
    )
    assert completed.status is BacktestStatus.COMPLETED
    assert completed.definition_schema_version == 2
    summary = completed.result_summary
    assert summary is not None and summary["engine_identifier"] != "ema-crossover-reference-v1"
    assert {"initial_capital", "final_equity", "trades", "equity_curve"} <= set(summary)
    assert completed.market_data_provider == "synthetic-local-v1"
    assert len(store.rows["AlgoProfitXBacktestTerminals"]) == 1
    again = await repository.get(strategy_version_id=queued.strategy_version_id, backtest_id=queued.id)
    assert again is not None and again.status is BacktestStatus.COMPLETED


@pytest.mark.asyncio
async def test_v1_backtest_still_uses_the_reference_engine(provision_schema_version_column):
    _, _, _, completed = await run_backtest(v1_backtest_version(), provision_schema_version_column)
    assert completed.status is BacktestStatus.COMPLETED
    assert completed.result_summary["engine_identifier"] == "ema-crossover-reference-v1"


@pytest.mark.asyncio
async def test_invalid_and_unsupported_definitions_fail_terminally_before_market_data(
    provision_schema_version_column, monkeypatch,
):
    loaded_data = AsyncMock()
    monkeypatch.setattr(
        "app.services.catalyst_backtest.SyntheticMarketDataProvider.load", loaded_data
    )
    broken = dataclasses.replace(v2_backtest_version(), configuration={"schema": "nonsense"})
    _, _, _, failed = await run_backtest(broken, provision_schema_version_column)
    assert failed.status is BacktestStatus.FAILED
    assert failed.error_code == "strategy_definition_invalid"

    unsupported = dataclasses.replace(v2_backtest_version(), definition_schema_version=3)
    _, _, _, failed = await run_backtest(unsupported, provision_schema_version_column)
    assert failed.status is BacktestStatus.FAILED
    assert failed.error_code == "strategy_definition_unsupported_version"
    loaded_data.assert_not_awaited()


# ------------------------------------------------------------------------------------ routes


def request():
    return SimpleNamespace()


def v2_request_body():
    return StrategyVersionV2CreateRequest(
        instrument_id=uuid.uuid4(),
        configuration=v2_document(),
        backtest_configuration=V2_ENV,
        definition_schema_version=2,
    )


@pytest.mark.asyncio
async def test_v2_create_route_stores_a_validated_definition_as_version_2(monkeypatch):
    strategy_id, creator_id = uuid.uuid4(), uuid.uuid4()
    created = SimpleNamespace(id=uuid.uuid4())
    repository = SimpleNamespace(
        get_strategy=AsyncMock(return_value=SimpleNamespace(id=strategy_id)),
        create_version=AsyncMock(return_value=created),
    )
    snapshot = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)
    monkeypatch.setattr(routes, "_validated_instrument_snapshot", AsyncMock(return_value=snapshot))
    body = v2_request_body()
    result = await routes.create_version_v2(
        strategy_id, body, request(), SimpleNamespace(id=creator_id), None
    )
    assert result is created
    kwargs = repository.create_version.await_args.kwargs
    assert kwargs["definition_schema_version"] == 2
    assert kwargs["configuration"] == body.configuration and kwargs["instrument"] is snapshot


@pytest.mark.asyncio
async def test_v2_create_route_reports_unprovisioned_storage_as_a_structured_503(monkeypatch):
    repository = SimpleNamespace(
        get_strategy=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        create_version=AsyncMock(side_effect=SchemaVersionColumnUnavailable(STRATEGY_VERSIONS_TABLE)),
    )
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)
    monkeypatch.setattr(routes, "_validated_instrument_snapshot", AsyncMock(return_value=SimpleNamespace()))
    with pytest.raises(routes.HTTPException) as raised:
        await routes.create_version_v2(
            uuid.uuid4(), v2_request_body(), request(), SimpleNamespace(id=uuid.uuid4()), None
        )
    assert raised.value.status_code == 503
    assert raised.value.detail["code"] == "strategy_definition_v2_storage_unavailable"
    assert STRATEGY_VERSIONS_TABLE not in str(raised.value.detail)  # no internal names leak


@pytest.mark.asyncio
async def test_v2_create_route_rejects_unrunnable_definitions_without_touching_storage(monkeypatch):
    repository = SimpleNamespace(
        get_strategy=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        create_version=AsyncMock(),
    )
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)
    bad = StrategyVersionV2CreateRequest(
        instrument_id=uuid.uuid4(),
        configuration={"schema": "invalid"},
        backtest_configuration=V2_ENV,
        definition_schema_version=2,
    )
    with pytest.raises(routes.HTTPException) as raised:
        await routes.create_version_v2(uuid.uuid4(), bad, request(), SimpleNamespace(id=uuid.uuid4()), None)
    assert raised.value.status_code == 422
    repository.create_version.assert_not_awaited()


@pytest.mark.asyncio
async def test_v1_create_route_refuses_a_v2_envelope_on_catalyst(monkeypatch):
    repository = SimpleNamespace(
        get_strategy=AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
        create_version=AsyncMock(),
    )
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)
    data = StrategyVersionCreateRequest(
        instrument_id=uuid.uuid4(), configuration={"schema": "x", "rules": []}, backtest_configuration={}
    )
    with pytest.raises(routes.HTTPException) as raised:
        await routes.create_version(
            uuid.uuid4(), data, request(), SimpleNamespace(id=uuid.uuid4()), SimpleNamespace()
        )
    assert raised.value.status_code == 422
    repository.create_version.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["publish", "deploy"])
async def test_lifecycle_routes_map_the_v2_gate_to_the_structured_409(monkeypatch, action):
    repository = SimpleNamespace(
        transition_strategy=AsyncMock(side_effect=UnsupportedExecutionVersionError(action, 2))
    )
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)
    with pytest.raises(routes.HTTPException) as raised:
        await getattr(routes, action)(
            uuid.uuid4(), request(), SimpleNamespace(id=uuid.uuid4()), SimpleNamespace()
        )
    assert raised.value.status_code == 409
    assert raised.value.detail["code"] == "strategy_definition_version_unsupported_for_execution"
