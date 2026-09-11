import hashlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.strategy import StrategyStatus
from app.models.instrument import InstrumentType
from app.persistence.catalyst.client import CatalystPersistenceError
from app.persistence.catalyst.strategy import (
    STRATEGIES_TABLE,
    CatalystStrategyRepository,
)
from app.persistence.strategy import DuplicateStrategySlug
from app.persistence.strategy import ExchangeSnapshotRecord, InstrumentSnapshotRecord


STRATEGY_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
CREATOR_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")


def strategy_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "ROWID": "36851000000000001",
        "strategy_uuid": str(STRATEGY_ID),
        "creator_uuid": str(CREATOR_ID),
        "name": "Momentum Strategy",
        "slug": "momentum-strategy",
        "slug_lookup": hashlib.sha256(b"momentum-strategy").hexdigest(),
        "description": "Example",
        "status": "draft",
        "is_public": False,
        "current_version_uuid": None,
        "created_at": "2026-09-09T06:30:00+00:00",
        "updated_at": "2026-09-09T06:30:00+00:00",
        "published_at": None,
        "deployed_at": None,
    }
    row.update(overrides)
    return row


def client() -> SimpleNamespace:
    return SimpleNamespace(
        async_query_rows=AsyncMock(),
        async_insert_row=AsyncMock(),
        async_update_row=AsyncMock(),
        async_delete_row=AsyncMock(),
    )


def instrument() -> InstrumentSnapshotRecord:
    moment = datetime(2026, 9, 9, 6, 30, tzinfo=timezone.utc)
    return InstrumentSnapshotRecord(
        id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
        exchange=ExchangeSnapshotRecord(
            id=uuid.UUID("55555555-5555-4555-8555-555555555555"),
            code="NSE",
            name="National Stock Exchange",
            country_code="IN",
            timezone="Asia/Kolkata",
            default_currency="INR",
            calendar_code="XNSE",
            is_active=True,
        ),
        canonical_symbol="TEST",
        exchange_symbol="TEST",
        name="Test Equity",
        instrument_type=InstrumentType.EQUITY,
        quote_currency="INR",
        tick_size=Decimal("0.05"),
        lot_size=1,
        is_tradeable=True,
        isin=None,
        is_synthetic=True,
        is_active=True,
        created_at=moment,
        updated_at=moment,
    )


def version_row(**overrides: object) -> dict[str, object]:
    selected = instrument()
    number = int(overrides.get("version_number", 1))
    row: dict[str, object] = {
        "ROWID": "version-row-1",
        "version_uuid": "66666666-6666-4666-8666-666666666666",
        "strategy_uuid": str(STRATEGY_ID),
        "version_key": hashlib.sha256(
            f"{STRATEGY_ID}:{number}".encode("ascii")
        ).hexdigest(),
        "instrument_uuid": str(selected.id),
        "version_number": number,
        "configuration": "{\"lookback\":20}",
        "backtest_configuration": "{}",
        "instrument_snapshot": __import__("json").dumps(
            CatalystStrategyRepository._instrument_payload(selected),
            sort_keys=True,
            separators=(",", ":"),
        ),
        "created_at": "2026-09-09T06:30:00+00:00",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_create_uses_hashed_slug_lookup_and_application_uuid():
    persistence = client()
    persistence.async_query_rows.return_value = []
    persistence.async_insert_row.return_value = {"ROWID": "row-1"}
    repository = CatalystStrategyRepository(persistence)

    created = await repository.create_strategy(
        creator_id=CREATOR_ID,
        name="Momentum Strategy",
        slug="momentum-strategy",
        description="Example",
    )

    assert created.creator_id == CREATOR_ID
    assert created.status is StrategyStatus.DRAFT
    table, payload = persistence.async_insert_row.await_args.args
    assert table == STRATEGIES_TABLE
    assert uuid.UUID(payload["strategy_uuid"])
    assert payload["slug_lookup"] == hashlib.sha256(b"momentum-strategy").hexdigest()


@pytest.mark.asyncio
async def test_duplicate_slug_is_rejected_before_insert():
    persistence = client()
    persistence.async_query_rows.return_value = [strategy_row()]
    repository = CatalystStrategyRepository(persistence)

    with pytest.raises(DuplicateStrategySlug, match="already in use"):
        await repository.create_strategy(
            creator_id=CREATOR_ID,
            name="Other Strategy",
            slug="momentum-strategy",
            description=None,
        )

    persistence.async_insert_row.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_unique_race_is_classified_after_confirming_slug():
    persistence = client()
    persistence.async_query_rows.side_effect = [[], [strategy_row()]]
    persistence.async_insert_row.side_effect = CatalystPersistenceError(
        "Catalyst row insert failed"
    )
    repository = CatalystStrategyRepository(persistence)

    with pytest.raises(DuplicateStrategySlug, match="already in use"):
        await repository.create_strategy(
            creator_id=CREATOR_ID,
            name="Other Strategy",
            slug="momentum-strategy",
            description=None,
        )


@pytest.mark.asyncio
async def test_owned_lookup_uses_only_validated_uuids():
    persistence = client()
    persistence.async_query_rows.return_value = [strategy_row()]
    repository = CatalystStrategyRepository(persistence)

    found = await repository.get_strategy(
        strategy_id=STRATEGY_ID, creator_id=CREATOR_ID
    )

    assert found is not None and found.id == STRATEGY_ID
    query, table = persistence.async_query_rows.await_args.args
    assert table == STRATEGIES_TABLE
    assert str(STRATEGY_ID) in query
    assert str(CREATOR_ID) in query


@pytest.mark.asyncio
async def test_list_sorts_newest_first_without_exposing_rowids():
    persistence = client()
    older = strategy_row()
    newer = strategy_row(
        ROWID="row-2",
        strategy_uuid="33333333-3333-4333-8333-333333333333",
        slug="newer-strategy",
        slug_lookup=hashlib.sha256(b"newer-strategy").hexdigest(),
        created_at="2026-09-10T06:30:00+00:00",
        updated_at="2026-09-10T06:30:00+00:00",
    )
    persistence.async_query_rows.return_value = [older, newer]
    repository = CatalystStrategyRepository(persistence)

    found = await repository.list_strategies(CREATOR_ID)

    assert [strategy.slug for strategy in found] == [
        "newer-strategy",
        "momentum-strategy",
    ]


@pytest.mark.asyncio
async def test_update_preserves_ownership_and_updates_slug_hash():
    persistence = client()
    persistence.async_query_rows.side_effect = [[strategy_row()], []]
    persistence.async_update_row.return_value = {"ROWID": "row-1"}
    repository = CatalystStrategyRepository(persistence)

    updated = await repository.update_strategy(
        strategy_id=STRATEGY_ID,
        creator_id=CREATOR_ID,
        updates={"name": "Updated Strategy", "slug": "updated-strategy"},
    )

    assert updated is not None and updated.name == "Updated Strategy"
    table, payload = persistence.async_update_row.await_args.args
    assert table == STRATEGIES_TABLE
    assert payload["ROWID"] == "36851000000000001"
    assert payload["slug_lookup"] == hashlib.sha256(b"updated-strategy").hexdigest()


@pytest.mark.asyncio
async def test_delete_allows_owned_draft_and_rejects_historical_state():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [strategy_row()],
        [],
        [strategy_row(status="published", is_public=True)],
    ]
    repository = CatalystStrategyRepository(persistence)

    assert await repository.delete_strategy(
        strategy_id=STRATEGY_ID, creator_id=CREATOR_ID
    )
    persistence.async_delete_row.assert_awaited_once_with(
        STRATEGIES_TABLE, "36851000000000001"
    )

    with pytest.raises(ValueError, match="unused draft"):
        await repository.delete_strategy(
            strategy_id=STRATEGY_ID, creator_id=CREATOR_ID
        )


@pytest.mark.asyncio
async def test_create_version_allocates_number_under_native_lock_and_round_trips_snapshot():
    persistence = client()
    lock_row = {
        "ROWID": "lock-row-1",
        "strategy_uuid": str(STRATEGY_ID),
        "owner_token": "pending",
        "acquired_at": "2026-09-09T06:30:00+00:00",
    }
    persistence.async_query_rows.side_effect = [
        [strategy_row()],
        [strategy_row()],
        [],
        [lock_row],
    ]
    persistence.async_insert_row.side_effect = [
        {"ROWID": "lock-row-1"},
        {"ROWID": "version-row-1"},
    ]
    repository = CatalystStrategyRepository(persistence)

    # Keep the generated owner token observable to the mocked release lookup.
    async def insert(table, payload):
        if table.endswith("Locks"):
            lock_row["owner_token"] = payload["owner_token"]
            return {"ROWID": "lock-row-1"}
        return {"ROWID": "version-row-1"}

    persistence.async_insert_row.side_effect = insert
    created = await repository.create_version(
        strategy_id=STRATEGY_ID,
        creator_id=CREATOR_ID,
        instrument=instrument(),
        configuration={"lookback": 20},
        backtest_configuration={},
    )

    assert created.version_number == 1
    assert created.instrument is not None
    assert created.instrument.exchange.code == "NSE"
    version_call = persistence.async_insert_row.await_args_list[1]
    assert version_call.args[0] == "AlgoProfitXStrategyVersions"
    assert "vendor" not in version_call.args[1]["instrument_snapshot"]
    persistence.async_delete_row.assert_awaited_once_with(
        "AlgoProfitXStrategyLocks", "lock-row-1"
    )


@pytest.mark.asyncio
async def test_publish_uses_latest_version_and_serialized_state_update():
    persistence = client()
    lock_row = {
        "ROWID": "lock-row-1",
        "strategy_uuid": str(STRATEGY_ID),
        "owner_token": "pending",
        "acquired_at": "2026-09-09T06:30:00+00:00",
    }

    async def insert(table, payload):
        if table.endswith("Locks"):
            lock_row["owner_token"] = payload["owner_token"]
        return {"ROWID": "lock-row-1"}

    persistence.async_insert_row.side_effect = insert
    persistence.async_query_rows.side_effect = [
        [strategy_row()],
        [version_row(version_number=1), version_row(
            ROWID="version-row-2",
            version_uuid="77777777-7777-4777-8777-777777777777",
            version_number=2,
            version_key=hashlib.sha256(f"{STRATEGY_ID}:2".encode("ascii")).hexdigest(),
        )],
        [lock_row],
    ]
    repository = CatalystStrategyRepository(persistence)

    published = await repository.transition_strategy(
        strategy_id=STRATEGY_ID,
        creator_id=CREATOR_ID,
        target=StrategyStatus.PUBLISHED,
    )

    assert published is not None
    assert published.status is StrategyStatus.PUBLISHED
    assert published.current_version_id == uuid.UUID(
        "77777777-7777-4777-8777-777777777777"
    )
    payload = persistence.async_update_row.await_args.args[1]
    assert payload["is_public"] is True


@pytest.mark.asyncio
async def test_fresh_native_lock_rejects_a_concurrent_lifecycle_command():
    persistence = client()
    persistence.async_insert_row.side_effect = CatalystPersistenceError(
        "Catalyst row insert failed"
    )
    persistence.async_query_rows.return_value = [{
        "ROWID": "lock-row-1",
        "strategy_uuid": str(STRATEGY_ID),
        "owner_token": "a" * 64,
        "acquired_at": datetime.now(timezone.utc).isoformat(),
    }]
    repository = CatalystStrategyRepository(persistence)

    with pytest.raises(ValueError, match="being updated"):
        await repository.transition_strategy(
            strategy_id=STRATEGY_ID,
            creator_id=CREATOR_ID,
            target=StrategyStatus.PUBLISHED,
        )

    persistence.async_update_row.assert_not_awaited()


@pytest.mark.asyncio
async def test_marketplace_filters_visibility_and_resolves_current_version():
    persistence = client()
    published = strategy_row(
        status="published",
        is_public=True,
        current_version_uuid="66666666-6666-4666-8666-666666666666",
        published_at="2026-09-09T07:00:00+00:00",
    )
    persistence.async_query_rows.side_effect = [
        [published, strategy_row(ROWID="draft-row")],
        [version_row()],
        [published],
        [version_row()],
    ]
    repository = CatalystStrategyRepository(persistence)

    listed = await repository.list_marketplace(limit=20, offset=0)
    selected = await repository.get_marketplace_by_slug("momentum-strategy")

    assert [(item.slug, number) for item, number in listed] == [
        ("momentum-strategy", 1)
    ]
    assert selected is not None
    assert selected[0].status is StrategyStatus.PUBLISHED
    assert selected[1] == 1


@pytest.mark.asyncio
async def test_marketplace_hides_archived_and_private_strategies():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [],
        [strategy_row(status="archived", is_public=False)],
    ]
    repository = CatalystStrategyRepository(persistence)

    assert await repository.list_marketplace(limit=20, offset=0) == []
    assert await repository.get_marketplace_by_slug("momentum-strategy") is None
