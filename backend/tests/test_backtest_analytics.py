import uuid

import pytest
from app.bootstrap.instruments import SYNTHETIC_EQUITY_ID
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.backtest import Backtest, BacktestStatus
from app.services.backtest import _claim_queued_backtest
from tests.test_backtest_execution import (
    backtests_path,
    client,
    create_backtest,
    create_strategy_version,
    execute_path,
    register_and_login,
)


def analytics_path(strategy: dict, version: dict, backtest: dict) -> str:
    return f"{backtests_path(strategy, version)}/{backtest['id']}/analytics"


async def replace_result_summary(backtest_id: str, summary: dict) -> None:
    async with AsyncSessionLocal() as session:
        backtest = await session.scalar(
            select(Backtest).where(Backtest.id == uuid.UUID(backtest_id))
        )
        assert backtest is not None
        backtest.result_summary = summary
        backtest.status = BacktestStatus.COMPLETED
        await session.commit()


@pytest.mark.asyncio
async def test_completed_backtest_analytics_are_deterministic(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "analytics-completed")
    backtest = await create_backtest(client, headers, strategy, version)
    execution = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert execution.status_code == 200

    response = await client.get(analytics_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 200
    analytics = response.json()
    result = execution.json()["result_summary"]
    assert analytics["backtest_id"] == backtest["id"]
    assert analytics["engine_identifier"] == result["engine_identifier"]
    assert analytics["provider_identifier"] == result["provider_identifier"]
    assert analytics["initial_capital"] == result["initial_capital"]
    assert analytics["final_equity"] == result["final_equity"]
    assert analytics["total_return"] == result["total_return"]
    assert analytics["trade_count"] == result["trade_count"] == 1
    assert analytics["win_rate"] == "1.00000000"
    assert analytics["profit_factor"] is None
    assert analytics["average_win"] == result["trades"][0]["pnl"]
    assert analytics["average_loss"] is None
    assert analytics["max_drawdown"] == "0.00000000"
    assert analytics["equity_curve"] == result["equity_curve"]
    assert analytics == (await client.get(analytics_path(strategy, version, backtest), headers=headers)).json()


@pytest.mark.asyncio
async def test_analytics_calculates_trade_metrics_and_closing_drawdown(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "analytics-metrics")
    backtest = await create_backtest(client, headers, strategy, version)
    await replace_result_summary(
        backtest["id"],
        {
            "initial_capital": "100",
            "final_equity": "110",
            "total_return": "10",
            "trades": [
                {"pnl": "20"},
                {"pnl": "-10"},
                {"pnl": "0"},
            ],
            "equity_curve": [
                {"timestamp": "2025-01-01T00:00:00+00:00", "equity": "100"},
                {"timestamp": "2025-01-01T01:00:00+00:00", "equity": "120"},
                {"timestamp": "2025-01-01T02:00:00+00:00", "equity": "90"},
                {"timestamp": "2025-01-01T03:00:00+00:00", "equity": "110"},
            ],
            "engine_identifier": "test-engine-v1",
            "provider_identifier": "test-provider-v1",
        },
    )

    response = await client.get(analytics_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 200
    analytics = response.json()
    assert analytics["trade_count"] == 3
    assert analytics["win_rate"] == "0.50000000"
    assert analytics["profit_factor"] == "2.00000000"
    assert analytics["average_win"] == "20.00000000"
    assert analytics["average_loss"] == "-10.00000000"
    assert analytics["max_drawdown"] == "25.00000000"
    assert analytics["equity_curve"][2]["equity"] == "90.00000000"


@pytest.mark.asyncio
async def test_analytics_zero_trades_and_empty_curve_return_null_metrics_and_zero_drawdown(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "analytics-empty")
    backtest = await create_backtest(client, headers, strategy, version)
    await replace_result_summary(
        backtest["id"],
        {
            "initial_capital": "100",
            "final_equity": "100",
            "total_return": "0",
            "trades": [],
            "equity_curve": [],
            "engine_identifier": "test-engine-v1",
            "provider_identifier": "test-provider-v1",
        },
    )

    response = await client.get(analytics_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 200
    analytics = response.json()
    assert analytics["trade_count"] == 0
    assert analytics["win_rate"] is None
    assert analytics["profit_factor"] is None
    assert analytics["average_win"] is None
    assert analytics["average_loss"] is None
    assert analytics["max_drawdown"] == "0.00000000"
    assert analytics["equity_curve"] == []


@pytest.mark.asyncio
async def test_analytics_requires_completed_backtest(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "analytics-status")
    queued = await create_backtest(client, headers, strategy, version)

    response = await client.get(analytics_path(strategy, version, queued), headers=headers)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Backtest must be completed before analytics can be requested"
    }

    async with AsyncSessionLocal() as session:
        await _claim_queued_backtest(session, uuid.UUID(queued["id"]))
    response = await client.get(analytics_path(strategy, version, queued), headers=headers)
    assert response.status_code == 409

    failed_strategy, failed_version = await create_strategy_version(
        client,
        headers,
        "analytics-failed",
        configuration={"entry": {"type": "unsupported"}},
    )
    failed = await create_backtest(client, headers, failed_strategy, failed_version)
    failed_execution = await client.post(
        execute_path(failed_strategy, failed_version, failed),
        headers=headers,
    )
    assert failed_execution.status_code == 200
    assert failed_execution.json()["status"] == "failed"
    response = await client.get(
        analytics_path(failed_strategy, failed_version, failed),
        headers=headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_analytics_requires_creator_and_preserves_ownership_hiding(client):
    owner_headers = await register_and_login(client)
    investor_headers = await register_and_login(client, enroll=False)
    other_creator_headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, owner_headers, "analytics-access")
    backtest = await create_backtest(client, owner_headers, strategy, version)
    path = analytics_path(strategy, version, backtest)

    assert (await client.get(path)).status_code == 401
    assert (await client.get(path, headers=investor_headers)).status_code == 403
    response = await client.get(path, headers=other_creator_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Strategy not found"}


@pytest.mark.asyncio
async def test_analytics_hides_backtest_version_mismatch(client):
    headers = await register_and_login(client)
    strategy, first_version = await create_strategy_version(client, headers, "analytics-mismatch")
    backtest = await create_backtest(client, headers, strategy, first_version)
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "instrument_id": str(SYNTHETIC_EQUITY_ID),
            "configuration": {
                "entry": {
                    "type": "ema_crossover",
                    "fast_period": 3,
                    "slow_period": 5,
                }
            },
            "backtest_configuration": {"initial_capital": "1000"},
        },
    )
    assert response.status_code == 201

    response = await client.get(
        analytics_path(strategy, response.json(), backtest),
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Backtest not found"}
