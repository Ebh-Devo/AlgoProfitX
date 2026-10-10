import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.strategy import StrategyStatus
from app.persistence.catalyst.allocation import (
    ALLOCATIONS_TABLE,
    CatalystAllocationConflict,
    CatalystAllocationRepository,
)
from app.persistence.strategy import StrategyRecord, StrategyVersionRecord


ALLOCATION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
INVESTOR_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
STRATEGY_ID = uuid.UUID("33333333-3333-4333-8333-333333333333")
VERSION_ID = uuid.UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)


def allocation_row(**overrides):
    row = {
        "ROWID": "allocation-row-1",
        "allocation_uuid": str(ALLOCATION_ID),
        "investor_uuid": str(INVESTOR_ID),
        "strategy_uuid": str(STRATEGY_ID),
        "strategy_version_uuid": str(VERSION_ID),
        "strategy_name": "Momentum",
        "strategy_version_number": 1,
        "notional_amount": "1000.50000000",
        "currency": "USD",
        "status": "active",
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
    }
    row.update(overrides)
    return row


def persistence():
    return SimpleNamespace(
        async_query_rows=AsyncMock(),
        async_insert_row=AsyncMock(),
        async_update_row=AsyncMock(),
        async_delete_row=AsyncMock(),
    )


def target():
    strategy = StrategyRecord(
        id=STRATEGY_ID,
        creator_id=uuid.uuid4(),
        name="Momentum",
        slug="momentum",
        description=None,
        status=StrategyStatus.DEPLOYED,
        is_public=True,
        current_version_id=VERSION_ID,
        created_at=NOW,
        updated_at=NOW,
        published_at=NOW,
        deployed_at=NOW,
    )
    version = StrategyVersionRecord(
        id=VERSION_ID,
        strategy_id=STRATEGY_ID,
        instrument_id=None,
        instrument=None,
        version_number=1,
        configuration={},
        backtest_configuration={},
        created_at=NOW,
    )
    return strategy, version


@pytest.mark.asyncio
async def test_create_snapshots_deployed_strategy_and_decimal():
    client = persistence()
    client.async_insert_row.return_value = {"ROWID": "allocation-row-1"}
    repository = CatalystAllocationRepository(client)
    repository._strategies.get_allocation_target = AsyncMock(return_value=target())

    created = await repository.create(
        investor_user_id=INVESTOR_ID,
        strategy_id=STRATEGY_ID,
        notional_amount=Decimal("1000.50000000"),
        currency="USD",
    )

    assert created.strategy_name == "Momentum"
    assert created.notional_amount == Decimal("1000.50000000")
    table, payload = client.async_insert_row.await_args.args
    assert table == ALLOCATIONS_TABLE
    assert uuid.UUID(payload["allocation_uuid"])
    assert payload["strategy_version_uuid"] == str(VERSION_ID)


@pytest.mark.asyncio
async def test_owned_queries_validate_uuid_and_hide_rowid():
    client = persistence()
    client.async_query_rows.return_value = [allocation_row()]
    repository = CatalystAllocationRepository(client)

    found = await repository.get_owned(ALLOCATION_ID, INVESTOR_ID)

    assert found is not None and found.id == ALLOCATION_ID
    query, table = client.async_query_rows.await_args.args
    assert table == ALLOCATIONS_TABLE
    assert str(ALLOCATION_ID) in query and str(INVESTOR_ID) in query


@pytest.mark.asyncio
async def test_update_only_changes_mutable_fields():
    client = persistence()
    client.async_query_rows.return_value = [allocation_row()]
    repository = CatalystAllocationRepository(client)

    updated = await repository.update_owned(
        allocation_id=ALLOCATION_ID,
        investor_user_id=INVESTOR_ID,
        updates={"notional_amount": Decimal("2500"), "currency": "INR"},
    )

    assert updated is not None and updated.currency == "INR"
    payload = client.async_update_row.await_args.args[1]
    assert payload["ROWID"] == "allocation-row-1"
    assert payload["notional_amount"] == "2500"


@pytest.mark.asyncio
async def test_delete_rejects_execution_history():
    client = persistence()
    client.async_query_rows.side_effect = [
        [allocation_row()],
        [{"ROWID": "execution-row-1"}],
    ]
    repository = CatalystAllocationRepository(client)

    with pytest.raises(CatalystAllocationConflict, match="execution intents"):
        await repository.delete_owned(ALLOCATION_ID, INVESTOR_ID)

    client.async_delete_row.assert_not_awaited()
