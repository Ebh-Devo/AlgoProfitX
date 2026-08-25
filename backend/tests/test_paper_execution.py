import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.bootstrap.instruments import NIFTY_50_INDEX_ID, SYNTHETIC_EQUITY_ID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.models.allocation import AllocationIntent
from app.models.execution import ExecutionIntent, ExecutionStatus
from app.models.strategy import Strategy, StrategyStatus
from app.paper_execution.reference import EmaCrossoverPaperAdapter
from tests.test_allocations import create_allocation
from tests.test_backtest_execution import (
    client,
    create_strategy_version,
    register_and_login,
)


EXECUTION_INTENTS_PATH = "/api/v1/execution-intents"


def test_lot_sizing_and_tick_quantization_use_canonical_metadata():
    assert EmaCrossoverPaperAdapter._quantity_for_notional(
        Decimal("1099"), Decimal("108.05"), Decimal("5")
    ) == Decimal("10")
    assert EmaCrossoverPaperAdapter._quantize_to_tick(
        Decimal("108.03"), Decimal("0.05")
    ) == Decimal("108.05")


def create_intent_path(allocation_id: str) -> str:
    return f"/api/v1/allocations/{allocation_id}/execution-intents"


def execute_path(execution_intent_id: str) -> str:
    return f"{EXECUTION_INTENTS_PATH}/{execution_intent_id}/execute"


async def create_paper_execution_intent(
    client,
    slug: str,
    configuration: dict | None = None,
    currency: str = "INR",
    amount: str = "1000.5",
    instrument_id: uuid.UUID = SYNTHETIC_EQUITY_ID,
):
    creator_headers = await register_and_login(client)
    investor_headers = await register_and_login(client, enroll=False)
    strategy, version = await create_strategy_version(
        client,
        creator_headers,
        slug,
        configuration=configuration,
        instrument_id=instrument_id,
    )
    assert (
        await client.post(
            f"/api/v1/strategies/{strategy['id']}/publish", headers=creator_headers
        )
    ).status_code == 200
    assert (
        await client.post(
            f"/api/v1/strategies/{strategy['id']}/deploy", headers=creator_headers
        )
    ).status_code == 200
    allocation_response = await create_allocation(
        client,
        investor_headers,
        strategy["id"],
        amount=amount,
        currency=currency,
    )
    assert allocation_response.status_code == 201
    allocation = allocation_response.json()
    intent_response = await client.post(
        create_intent_path(allocation["id"]), headers=investor_headers, json={}
    )
    assert intent_response.status_code == 201
    return creator_headers, investor_headers, strategy, version, allocation, intent_response.json()


@pytest.mark.asyncio
async def test_paper_execution_completes_with_deterministic_bounded_buy_result(client):
    _, investor_headers, strategy, version, allocation, intent = (
        await create_paper_execution_intent(client, "paper-success")
    )
    response = await client.post(execute_path(intent["id"]), headers=investor_headers)
    assert response.status_code == 200
    completed = response.json()
    result = completed["paper_result_summary"]
    assert completed["status"] == "completed"
    assert completed["started_at"] is not None
    assert completed["completed_at"] is not None
    assert completed["error_code"] is None
    assert completed["error_message"] is None
    assert result == {
        "engine_identifier": "ema-crossover-paper-reference-v1",
        "provider_identifier": "synthetic-paper-nse-equity-v1",
        "instrument_id": str(SYNTHETIC_EQUITY_ID),
        "canonical_symbol": "TRADEEBH_TEST_EQ",
        "exchange_symbol": "TRADEEBH_TEST_EQ",
        "name": "TradeEBH Synthetic Reference Equity (not a real security)",
        "exchange_code": "NSE",
        "exchange": "NSE",
        "instrument_type": "equity",
        "quote_currency": "INR",
        "is_tradeable": True,
        "lot_size": 1,
        "tick_size": "0.01",
        "signal": "buy",
        "execution_outcome": "filled",
        "no_fill_reason": None,
        "notional_amount": "1000.50000000",
        "order": {
            "side": "buy",
            "quantity": "9",
            "requested_price": "108.00",
            "reference_price": "108.00",
            "timestamp": "2025-01-01T07:45:00+00:00",
        },
        "fill": {
            "quantity": "9",
            "price": "108.00",
            "timestamp": "2025-01-01T07:45:00+00:00",
        },
        "position": {"quantity": "9", "average_price": "108.00"},
    }
    assert len(json.dumps(result, sort_keys=True).encode("utf-8")) <= 8_192
    assert completed["strategy_id"] == strategy["id"]
    assert completed["strategy_version_id"] == version["id"]
    assert completed["allocation_intent_id"] == allocation["id"]

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(ExecutionIntent).where(ExecutionIntent.id == uuid.UUID(intent["id"]))
        )
    assert persisted is not None
    assert persisted.status == ExecutionStatus.COMPLETED
    assert persisted.paper_result_summary == result
    fill_timestamp = datetime.fromisoformat(result["fill"]["timestamp"])
    assert fill_timestamp.tzinfo is not None
    assert fill_timestamp.utcoffset() == timezone.utc.utcoffset(fill_timestamp)
    india_standard_time = timezone(timedelta(hours=5, minutes=30))
    assert fill_timestamp.astimezone(india_standard_time).isoformat() == "2025-01-01T13:15:00+05:30"


@pytest.mark.asyncio
async def test_paper_execution_latest_only_and_decimal_rounding(client):
    configuration = {
        "instrument": "TRADEEBH_TEST_EQ",
        "entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 5},
        "paper_execution_scenario": "historical_crossover",
    }
    _, investor_headers, _, _, _, historical_intent = await create_paper_execution_intent(
        client,
        "paper-historical",
        configuration=configuration,
    )
    response = await client.post(
        execute_path(historical_intent["id"]), headers=investor_headers
    )
    assert response.status_code == 200
    historical = response.json()["paper_result_summary"]
    assert historical["signal"] == "none"
    assert historical["order"] is None
    assert historical["fill"] is None
    assert historical["execution_outcome"] == "no_signal"
    assert historical["position"] == {"quantity": "0", "average_price": None}

    no_signal_configuration = {
        "instrument": "TRADEEBH_TEST_EQ",
        "entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 5},
        "paper_execution_scenario": "no_signal",
    }
    _, investor_headers, _, _, _, no_signal_intent = await create_paper_execution_intent(
        client,
        "paper-no-signal",
        configuration=no_signal_configuration,
    )
    response = await client.post(
        execute_path(no_signal_intent["id"]), headers=investor_headers
    )
    assert response.status_code == 200
    assert response.json()["paper_result_summary"]["signal"] == "none"

    _, investor_headers, _, _, _, rounded_intent = await create_paper_execution_intent(
        client,
        "paper-rounding",
        amount="1079.99999999",
    )
    response = await client.post(execute_path(rounded_intent["id"]), headers=investor_headers)
    assert response.status_code == 200
    assert response.json()["paper_result_summary"]["order"]["quantity"] == "9"

    _, investor_headers, _, _, _, insufficient_intent = await create_paper_execution_intent(
        client,
        "paper-insufficient-notional",
        amount="107.99",
    )
    response = await client.post(
        execute_path(insufficient_intent["id"]), headers=investor_headers
    )
    assert response.status_code == 200
    insufficient = response.json()["paper_result_summary"]
    assert insufficient["signal"] == "buy"
    assert insufficient["execution_outcome"] == "no_fill"
    assert insufficient["no_fill_reason"] == "insufficient_notional_for_one_lot"
    assert insufficient["order"] is None
    assert insufficient["fill"] is None
    assert insufficient["position"] == {"quantity": "0", "average_price": None}


@pytest.mark.asyncio
async def test_paper_execution_failures_are_terminal_and_sanitized(client):
    invalid_configuration = {
        "instrument": "TRADEEBH_TEST_EQ",
        "entry": {"type": "unsupported"},
    }
    _, investor_headers, _, _, _, invalid_intent = await create_paper_execution_intent(
        client,
        "paper-invalid",
        configuration=invalid_configuration,
    )
    response = await client.post(execute_path(invalid_intent["id"]), headers=investor_headers)
    assert response.status_code == 200
    failed = response.json()
    assert failed["status"] == "failed"
    assert failed["error_code"] == "invalid_strategy_configuration"
    assert failed["paper_result_summary"] is None
    assert "\n" not in failed["error_message"]
    assert len(failed["error_message"]) <= 500
    response = await client.post(execute_path(invalid_intent["id"]), headers=investor_headers)
    assert response.status_code == 409

    unsupported_configuration = {
        "entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 5},
    }
    _, investor_headers, _, _, _, unsupported_intent = await create_paper_execution_intent(
        client,
        "paper-instrument",
        configuration=unsupported_configuration,
    )
    response = await client.post(execute_path(unsupported_intent["id"]), headers=investor_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["paper_result_summary"]["canonical_symbol"] == "TRADEEBH_TEST_EQ"

    _, investor_headers, _, _, _, currency_intent = await create_paper_execution_intent(
        client,
        "paper-currency",
        currency="USD",
    )
    response = await client.post(execute_path(currency_intent["id"]), headers=investor_headers)
    assert response.status_code == 200
    assert response.json()["error_code"] == "currency_mismatch"


@pytest.mark.asyncio
async def test_non_tradeable_index_is_pinned_but_rejected_for_execution(client):
    _, investor_headers, _, _, _, intent = await create_paper_execution_intent(
        client,
        "paper-index",
        configuration={"entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 5}},
        instrument_id=NIFTY_50_INDEX_ID,
    )
    assert intent["instrument_snapshot"]["instrument_type"] == "index"
    assert intent["instrument_snapshot"]["is_tradeable"] is False

    response = await client.post(execute_path(intent["id"]), headers=investor_headers)

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error_code"] == "instrument_not_tradeable"


@pytest.mark.asyncio
async def test_paper_execution_revalidates_strategy_and_preserves_terminal_states(client):
    creator_headers, investor_headers, strategy, _, _, intent = (
        await create_paper_execution_intent(client, "paper-lifecycle")
    )
    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )
        assert persisted is not None
        persisted.status = StrategyStatus.ARCHIVED
        persisted.is_public = False
        await session.commit()
    response = await client.post(execute_path(intent["id"]), headers=investor_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error_code"] == "strategy_not_executable"

    _, investor_headers, _, _, _, completed_intent = await create_paper_execution_intent(
        client, "paper-completed-conflict"
    )
    assert (
        await client.post(execute_path(completed_intent["id"]), headers=investor_headers)
    ).status_code == 200
    response = await client.post(execute_path(completed_intent["id"]), headers=investor_headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Execution intent cannot execute while completed"}
    assert creator_headers


@pytest.mark.asyncio
async def test_paper_execution_claim_is_concurrent_safe_and_hides_ownership(client):
    _, investor_headers, _, _, _, intent = await create_paper_execution_intent(
        client, "paper-concurrency"
    )
    first, second = await asyncio.gather(
        client.post(execute_path(intent["id"]), headers=investor_headers),
        client.post(execute_path(intent["id"]), headers=investor_headers),
    )
    assert sorted((first.status_code, second.status_code)) == [200, 409]

    other_investor_headers = await register_and_login(client, enroll=False)
    response = await client.post(
        execute_path(intent["id"]), headers=other_investor_headers
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Execution intent not found"}
    assert (await client.post(execute_path(intent["id"]))).status_code == 401


@pytest.mark.asyncio
async def test_allocation_delete_is_blocked_when_execution_history_exists(client):
    _, investor_headers, strategy, _, allocation, intent = (
        await create_paper_execution_intent(client, "paper-delete-protection")
    )
    response = await client.delete(
        f"/api/v1/allocations/{allocation['id']}", headers=investor_headers
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Allocation with execution intents cannot be deleted"}


@pytest.mark.asyncio
async def test_strategy_delete_is_blocked_and_preserves_investor_history(client):
    creator_headers, investor_headers, strategy, _, allocation, intent = (
        await create_paper_execution_intent(client, "strategy-delete-history")
    )

    response = await client.delete(
        f"/api/v1/strategies/{strategy['id']}", headers=creator_headers
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Strategy with allocation or execution history cannot be deleted"
    }
    assert (
        await client.get(
            f"/api/v1/allocations/{allocation['id']}", headers=investor_headers
        )
    ).status_code == 200
    assert (
        await client.get(
            f"/api/v1/execution-intents/{intent['id']}", headers=investor_headers
        )
    ).status_code == 200
    assert (
        await client.get(f"{EXECUTION_INTENTS_PATH}/{intent['id']}", headers=investor_headers)
    ).status_code == 200

    response = await create_allocation(client, investor_headers, strategy["id"])
    assert response.status_code == 201
    unexecuted_allocation = response.json()
    assert (
        await client.delete(
            f"/api/v1/allocations/{unexecuted_allocation['id']}", headers=investor_headers
        )
    ).status_code == 204

    async with AsyncSessionLocal() as session:
        protected = await session.scalar(
            select(AllocationIntent).where(AllocationIntent.id == uuid.UUID(allocation["id"]))
        )
        assert protected is not None
        await session.delete(protected)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()
