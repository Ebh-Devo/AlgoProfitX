"""Phase 6: persisted definition_schema_version, and V1/V2 routing in the backtest service."""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text

from app.bootstrap.instruments import SYNTHETIC_EQUITY_ID
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.backtest import Backtest
from app.models.market_data import MarketDataDataset
from app.models.strategy import Strategy, StrategyVersion
from app.services import backtest as backtest_service
from app.services.strategy import (
    StrategyVersionValidationError,
    create_strategy_version_v2,
)
from app.strategy_definition.runtime.engine import StrategyRuntimeEngine
from app.strategy_definition.schema import CrossCondition, SharesSizing
from tests.strategy_v2_builders import D, ind, leg, long_definition, op, position, rule
from tests.test_backtest_execution import (
    backtests_path,
    create_backtest,
    create_strategy_version,
    execute_path,
    register_and_login,
)

V2_BACKTEST_CONFIGURATION = {
    "initial_capital": "10000",
    "fill_model": "same_bar_close",
    "timeframe": "1d",
    "start_date": "2025-01-01T00:00:00Z",
}


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


def v2_document(shares: int = 5, **changes) -> dict:
    return long_definition(
        positions=(position(legs=[leg()], sizing=SharesSizing(D(shares))),),
        rules=(
            rule("enter", CrossCondition("above", ind("ema", 3), ind("ema", 5)), [op("open")]),
            rule("exit", CrossCondition("below", ind("ema", 3), ind("ema", 5)), [op("close")]),
        ),
        **changes,
    ).to_dict()


def only_close_document() -> dict:
    """Semantically invalid: it closes a position nothing ever opens."""
    return long_definition(
        rules=(rule("x", CrossCondition("below", ind("ema", 3), ind("ema", 9)), [op("close")]),)
    ).to_dict()


async def new_strategy(client, headers, slug) -> dict:
    response = await client.post(
        "/api/v1/strategies", headers=headers, json={"name": f"Wiring {slug}", "slug": slug}
    )
    assert response.status_code == 201
    return response.json()


async def make_v2_version(
    strategy: dict,
    configuration: dict | None = None,
    backtest_configuration: dict | None = None,
) -> dict:
    """V2 creation is internal (no public API yet): go through the service entry point."""
    async with AsyncSessionLocal() as session:
        row = await session.get(Strategy, uuid.UUID(strategy["id"]))
        version = await create_strategy_version_v2(
            session,
            row,
            instrument_id=SYNTHETIC_EQUITY_ID,
            configuration=configuration if configuration is not None else v2_document(),
            backtest_configuration=backtest_configuration or V2_BACKTEST_CONFIGURATION,
        )
        await session.commit()
        return {"id": str(version.id)}


async def overwrite_configuration(version: dict, configuration: dict) -> None:
    """Corrupt a stored row after creation, as a bad historical/hand-edited row would be."""
    async with AsyncSessionLocal() as session:
        row = await session.get(StrategyVersion, uuid.UUID(version["id"]))
        row.configuration = configuration
        await session.commit()


async def run_backtest(client, headers, strategy, version) -> dict:
    backtest = await create_backtest(client, headers, strategy, version)
    response = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def no_data_or_runtime(monkeypatch):
    """Fail loudly if a doomed backtest reaches market data or the runtime."""
    touched: list[str] = []

    async def acquire(*args, **kwargs):
        touched.append("market_data")
        raise AssertionError("market data was requested before the definition was validated")

    def run_canonical(self, *args, **kwargs):
        touched.append("runtime")
        raise AssertionError("the runtime ran before the definition was validated")

    monkeypatch.setattr(backtest_service, "_acquire_dataset", acquire)
    monkeypatch.setattr(StrategyRuntimeEngine, "run_canonical", run_canonical)
    return touched


# --- persistence --------------------------------------------------------------------------


async def test_v1_creation_persists_version_1_and_the_response_shape_is_unchanged(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "persist-v1")
    assert version["definition_schema_version"] == 1
    async with AsyncSessionLocal() as session:
        row = await session.get(StrategyVersion, uuid.UUID(version["id"]))
        assert row.definition_schema_version == 1


async def test_v2_round_trips_with_version_2_and_untouched_json(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "persist-v2")
    document = v2_document()
    version = await make_v2_version(strategy, document)
    async with AsyncSessionLocal() as session:
        row = await session.get(StrategyVersion, uuid.UUID(version["id"]))
        assert row.definition_schema_version == 2
        assert row.configuration == document
    # still readable through the existing read endpoint, unchanged shape
    response = await client.get(
        f"/api/v1/strategies/{strategy['id']}/versions/{version['id']}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["configuration"] == document
    assert response.json()["definition_schema_version"] == 2


async def test_a_historical_row_without_the_column_value_reads_as_v1(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "persist-legacy")
    version_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        # exactly what a pre-Phase-6 writer produced: no definition_schema_version in the INSERT
        await session.execute(
            text(
                "INSERT INTO strategy_versions (id, strategy_id, instrument_id, version_number, "
                "configuration, backtest_configuration) VALUES (:id, :sid, :iid, 1, "
                "CAST(:cfg AS jsonb), CAST(:bt AS jsonb))"
            ),
            {
                "id": version_id,
                "sid": uuid.UUID(strategy["id"]),
                "iid": SYNTHETIC_EQUITY_ID,
                "cfg": '{"entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 5}}',
                "bt": '{"initial_capital": "1000"}',
            },
        )
        await session.commit()
    async with AsyncSessionLocal() as session:
        row = await session.get(StrategyVersion, version_id)
        assert row.definition_schema_version == 1
    completed = await run_backtest(client, headers, strategy, {"id": str(version_id)})
    assert completed["status"] == "completed"
    assert completed["result_summary"]["engine_identifier"] == "ema-crossover-reference-v1"


async def test_the_public_v1_endpoint_refuses_a_v2_envelope_instead_of_storing_it_as_v1(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "no-mislabel")
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "instrument_id": str(SYNTHETIC_EQUITY_ID),
            "configuration": v2_document(),
            "backtest_configuration": V2_BACKTEST_CONFIGURATION,
        },
    )
    assert response.status_code == 422
    async with AsyncSessionLocal() as session:
        assert list((await session.scalars(select(StrategyVersion))).all()) == []


async def test_v2_creation_validates_before_persisting(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "create-invalid-v2")
    for bad in ({"schema_version": 2}, only_close_document()):
        with pytest.raises(StrategyVersionValidationError):
            await make_v2_version(strategy, bad)
    async with AsyncSessionLocal() as session:
        assert list((await session.scalars(select(StrategyVersion))).all()) == []


async def test_the_backtest_snapshots_the_schema_version(client):
    headers = await register_and_login(client)
    strategy, v1 = await create_strategy_version(client, headers, "snapshot-v1")
    v2_strategy = await new_strategy(client, headers, "snapshot-v2")
    v2 = await make_v2_version(v2_strategy)
    first = await create_backtest(client, headers, strategy, v1)
    second = await create_backtest(client, headers, v2_strategy, v2)
    async with AsyncSessionLocal() as session:
        assert (await session.get(Backtest, uuid.UUID(first["id"]))).definition_schema_version == 1
        assert (await session.get(Backtest, uuid.UUID(second["id"]))).definition_schema_version == 2
    assert first["definition_schema_version"] == 1


# --- V2 execution -------------------------------------------------------------------------


async def test_a_valid_v2_definition_runs_through_the_phase5_runtime(client, monkeypatch):
    calls = []
    original = StrategyRuntimeEngine.run_canonical

    def spy(self, canonical, backtest_configuration, candles):
        calls.append((canonical.source_schema_version, len(candles)))
        return original(self, canonical, backtest_configuration, candles)

    monkeypatch.setattr(StrategyRuntimeEngine, "run_canonical", spy)
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "run-v2")
    version = await make_v2_version(strategy)
    completed = await run_backtest(client, headers, strategy, version)

    assert calls == [(2, 64)]
    assert completed["status"] == "completed"
    summary = completed["result_summary"]
    assert summary["engine_identifier"] == "strategy-runtime-v2"
    assert summary["provider_identifier"] == "synthetic-local-v1"
    assert summary["initial_capital"] == "10000.00000000"
    # the existing result boundary: same keys as the V1 summary
    assert set(summary) == {
        "initial_capital", "final_equity", "total_return", "trade_count", "trades",
        "equity_curve", "engine_identifier", "provider_identifier",
    }
    assert summary["trade_count"] == len(summary["trades"]) == 1
    assert len(summary["equity_curve"]) == 64
    trade = summary["trades"][0]
    assert {"side", "entry_timestamp", "exit_timestamp", "quantity", "entry_price", "exit_price", "pnl"} <= set(trade)
    assert trade["quantity"] == "5.00000000"
    assert trade["exit_reason"] == "end_of_data"  # synthetic data never crosses back down
    assert completed["market_data_provider"] == "synthetic"

    # the existing analytics endpoint consumes the V2 summary unchanged
    analytics = await client.get(
        f"{backtests_path(strategy, version)}/{completed['id']}/analytics", headers=headers
    )
    assert analytics.status_code == 200
    assert analytics.json()["trade_count"] == 1

    async with AsyncSessionLocal() as session:
        assert (await session.get(Backtest, uuid.UUID(completed["id"]))).definition_schema_version == 2


async def test_v2_execution_is_deterministic(client):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "run-v2-deterministic")
    version = await make_v2_version(strategy)
    first = await run_backtest(client, headers, strategy, version)
    second = await run_backtest(client, headers, strategy, version)
    assert first["result_summary"] == second["result_summary"]


async def test_an_invalid_v2_definition_fails_before_market_data_and_runtime(client, no_data_or_runtime):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "fail-semantic")
    version = await make_v2_version(strategy)
    await overwrite_configuration(version, only_close_document())
    completed = await run_backtest(client, headers, strategy, version)
    assert completed["status"] == "failed"
    assert completed["error_code"] == "strategy_definition_invalid"
    assert completed["result_summary"] is None
    assert no_data_or_runtime == []


async def test_a_malformed_v2_definition_fails_before_market_data_and_runtime(client, no_data_or_runtime):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "fail-malformed")
    version = await make_v2_version(strategy)
    await overwrite_configuration(version, {"schema_version": 2})
    completed = await run_backtest(client, headers, strategy, version)
    assert completed["status"] == "failed"
    assert completed["error_code"] == "strategy_definition_invalid"
    assert no_data_or_runtime == []


async def test_an_unsupported_capability_fails_before_market_data_and_runtime(client, no_data_or_runtime):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "fail-capability")
    two_legs = long_definition(positions=(position(legs=[leg("a"), leg("b")]),)).to_dict()
    version = await make_v2_version(strategy, two_legs)  # valid, so it may be stored
    completed = await run_backtest(client, headers, strategy, version)
    assert completed["status"] == "failed"
    assert completed["error_code"] == "strategy_definition_unsupported_capability"
    assert "multi_leg.basket" in completed["error_message"]
    assert no_data_or_runtime == []


async def test_an_invalid_v2_environment_fails_before_market_data_and_runtime(client, no_data_or_runtime):
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "fail-environment")
    version = await make_v2_version(
        strategy, backtest_configuration={"initial_capital": "10000"}  # no fill_model
    )
    completed = await run_backtest(client, headers, strategy, version)
    assert completed["status"] == "failed"
    assert completed["error_code"] == "strategy_environment_invalid"
    assert no_data_or_runtime == []


async def test_an_unsupported_schema_version_fails_deterministically_without_fallback(client, no_data_or_runtime):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "fail-unsupported")
    async with AsyncSessionLocal() as session:
        await session.execute(
            text("UPDATE strategy_versions SET definition_schema_version = 3 WHERE id = :id"),
            {"id": uuid.UUID(version["id"])},
        )
        await session.commit()
    completed = await run_backtest(client, headers, strategy, version)
    assert completed["status"] == "failed"
    assert completed["error_code"] == "strategy_definition_unsupported_version"
    assert no_data_or_runtime == []
    async with AsyncSessionLocal() as session:
        assert list((await session.scalars(select(MarketDataDataset))).all()) == []


# --- V1 stays on the V1 path -----------------------------------------------------------------


async def test_v1_never_touches_the_v2_runtime(client, monkeypatch):
    def forbidden(self, *args, **kwargs):
        raise AssertionError("a V1 version reached the V2 runtime")

    monkeypatch.setattr(StrategyRuntimeEngine, "run_canonical", forbidden)
    monkeypatch.setattr(StrategyRuntimeEngine, "run", forbidden)
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "v1-path")
    completed = await run_backtest(client, headers, strategy, version)
    assert completed["status"] == "completed"
    assert completed["result_summary"]["engine_identifier"] == "ema-crossover-reference-v1"
    assert completed["result_summary"]["trade_count"] == 1
