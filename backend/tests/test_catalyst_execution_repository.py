import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.execution import ExecutionStatus
from app.models.strategy import StrategyStatus
from app.models.instrument import InstrumentType
from app.persistence.allocation import AllocationRecord
from app.persistence.catalyst.execution import (
    EXECUTION_CLAIMS_TABLE,
    EXECUTIONS_TABLE,
    CatalystExecutionRepository,
)
from app.persistence.strategy import (
    ExchangeSnapshotRecord,
    InstrumentSnapshotRecord,
    StrategyRecord,
    StrategyVersionRecord,
)


INVESTOR_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
ALLOCATION_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
STRATEGY_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
VERSION_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
INSTRUMENT_ID = uuid.UUID("55555555-5555-4555-8555-555555555555")
EXECUTION_ID = uuid.UUID("66666666-6666-4666-8666-666666666666")
NOW = datetime(2026, 9, 12, 9, 0, tzinfo=timezone.utc)


def client():
    return SimpleNamespace(
        async_query_rows=AsyncMock(),
        async_insert_row=AsyncMock(),
        async_update_row=AsyncMock(),
        async_delete_row=AsyncMock(),
    )


def allocation():
    return AllocationRecord(
        id=ALLOCATION_ID,
        investor_user_id=INVESTOR_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=VERSION_ID,
        strategy_name="Momentum",
        strategy_version_number=1,
        notional_amount=Decimal("1000"),
        currency="INR",
        status=__import__('app.models.allocation', fromlist=['AllocationStatus']).AllocationStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


def target():
    exchange = ExchangeSnapshotRecord(
        id=uuid.uuid4(), code="NSE", name="NSE", country_code="IN",
        timezone="Asia/Kolkata", default_currency="INR", calendar_code="XNSE",
        is_active=True,
    )
    instrument = InstrumentSnapshotRecord(
        id=INSTRUMENT_ID, exchange=exchange, canonical_symbol="ALGOPROFITX_TEST_EQ",
        exchange_symbol="ALGOPROFITX_TEST_EQ", name="Test", instrument_type=InstrumentType.EQUITY,
        quote_currency="INR", tick_size=Decimal("0.05"), lot_size=1,
        is_tradeable=True, isin=None, is_synthetic=True, is_active=True,
        created_at=NOW, updated_at=NOW,
    )
    strategy = StrategyRecord(
        id=STRATEGY_ID, creator_id=uuid.uuid4(), name="Momentum", slug="momentum",
        description=None, status=StrategyStatus.DEPLOYED, is_public=True,
        current_version_id=VERSION_ID, created_at=NOW, updated_at=NOW,
        published_at=NOW, deployed_at=NOW,
    )
    version = StrategyVersionRecord(
        id=VERSION_ID, strategy_id=STRATEGY_ID, instrument_id=INSTRUMENT_ID,
        instrument=instrument, version_number=1,
        configuration={"entry":{"type":"ema_crossover","fast_period":2,"slow_period":5}},
        backtest_configuration={}, created_at=NOW,
    )
    return strategy, version


def execution_row(**overrides):
    row = {
        "ROWID": "execution-row-1", "execution_uuid": str(EXECUTION_ID),
        "allocation_uuid": str(ALLOCATION_ID), "investor_uuid": str(INVESTOR_ID),
        "strategy_uuid": str(STRATEGY_ID), "strategy_version_uuid": str(VERSION_ID),
        "instrument_uuid": str(INSTRUMENT_ID), "instrument_snapshot": json.dumps({"canonical_symbol":"ALGOPROFITX_TEST_EQ"}),
        "strategy_name": "Momentum", "strategy_version_number": 1,
        "notional_amount": "1000", "currency": "INR", "mode": "paper",
        "status": "pending", "idempotency_key": None, "idempotency_lookup": None,
        "created_at": NOW.isoformat(), "started_at": None, "completed_at": None,
        "error_code": None, "error_message": None, "paper_result_summary": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_create_claims_allocation_and_snapshots_version():
    persistence = client()
    persistence.async_query_rows.return_value = []
    persistence.async_insert_row.side_effect = [
        {"ROWID": "claim-row-1"}, {"ROWID": "execution-row-1"}
    ]
    repository = CatalystExecutionRepository(persistence)
    repository.allocations.get_owned = AsyncMock(return_value=allocation())
    repository.strategies.get_execution_target = AsyncMock(return_value=target())

    created, was_created = await repository.create(
        allocation_id=ALLOCATION_ID, investor_id=INVESTOR_ID,
        idempotency_key="client-key",
    )

    assert was_created and created.status is ExecutionStatus.PENDING
    assert persistence.async_insert_row.await_args_list[0].args[0] == EXECUTION_CLAIMS_TABLE
    assert persistence.async_insert_row.await_args_list[1].args[0] == EXECUTIONS_TABLE


@pytest.mark.asyncio
async def test_claim_and_finish_release_native_claim():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [execution_row()],
        [execution_row(status="running", started_at=NOW.isoformat())],
        [{"ROWID":"claim-row-1", "allocation_uuid":str(ALLOCATION_ID), "execution_uuid":str(EXECUTION_ID), "created_at":NOW.isoformat()}],
    ]
    repository = CatalystExecutionRepository(persistence)

    running = await repository.claim(EXECUTION_ID, INVESTOR_ID)
    completed = await repository.finish(
        EXECUTION_ID, INVESTOR_ID, result={"execution_outcome":"filled"}
    )

    assert running.status is ExecutionStatus.RUNNING
    assert completed.status is ExecutionStatus.COMPLETED
    persistence.async_delete_row.assert_awaited_once_with(EXECUTION_CLAIMS_TABLE, "claim-row-1")
