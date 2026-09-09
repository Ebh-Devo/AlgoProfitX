import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.strategy import StrategyStatus
from app.persistence.catalyst.client import CatalystPersistenceError
from app.persistence.catalyst.strategy import (
    STRATEGIES_TABLE,
    CatalystStrategyRepository,
)
from app.persistence.strategy import DuplicateStrategySlug


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
