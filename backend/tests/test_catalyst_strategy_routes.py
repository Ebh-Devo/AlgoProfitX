import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.api.routes import strategies as routes
from app.models.strategy import StrategyStatus
from app.schemas.strategy import StrategyCreateRequest, StrategyVersionCreateRequest


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/"})


@pytest.mark.asyncio
async def test_development_create_uses_catalyst_without_postgres_commit(monkeypatch):
    creator_id = uuid.uuid4()
    created = SimpleNamespace(id=uuid.uuid4(), creator_id=creator_id)
    repository = SimpleNamespace(create_strategy=AsyncMock(return_value=created))
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)
    legacy = AsyncMock(side_effect=AssertionError("legacy strategy write used"))
    monkeypatch.setattr(routes, "create_strategy", legacy)

    result = await routes.create(
        StrategyCreateRequest(name="Momentum Strategy", slug="momentum-strategy"),
        request(),
        SimpleNamespace(id=creator_id),
        session,
    )

    assert result is created
    repository.create_strategy.assert_awaited_once()
    session.commit.assert_not_awaited()
    legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_development_version_uses_validated_snapshot_and_catalyst(monkeypatch):
    creator_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    instrument_id = uuid.uuid4()
    strategy = SimpleNamespace(id=strategy_id)
    snapshot = SimpleNamespace(id=instrument_id)
    created = SimpleNamespace(id=uuid.uuid4())
    repository = SimpleNamespace(
        get_strategy=AsyncMock(return_value=strategy),
        create_version=AsyncMock(return_value=created),
    )
    validator = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)
    monkeypatch.setattr(routes, "_validated_instrument_snapshot", validator)

    data = StrategyVersionCreateRequest(
        instrument_id=instrument_id,
        configuration={"lookback": 20},
        backtest_configuration={},
    )
    result = await routes.create_version(
        strategy_id,
        data,
        request(),
        SimpleNamespace(id=creator_id),
        SimpleNamespace(),
    )

    assert result is created
    validator.assert_awaited_once()
    repository.create_version.assert_awaited_once_with(
        strategy_id=strategy_id,
        creator_id=creator_id,
        instrument=snapshot,
        configuration={"lookback": 20},
        backtest_configuration={},
        definition_schema_version=1,
    )


@pytest.mark.asyncio
async def test_development_publish_uses_serialized_catalyst_transition(monkeypatch):
    creator_id = uuid.uuid4()
    strategy_id = uuid.uuid4()
    published = SimpleNamespace(id=strategy_id, status=StrategyStatus.PUBLISHED)
    repository = SimpleNamespace(
        transition_strategy=AsyncMock(return_value=published)
    )
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(routes, "_uses_catalyst_strategies", lambda: True)
    monkeypatch.setattr(routes, "_catalyst_repository", lambda _: repository)

    result = await routes.publish(
        strategy_id,
        request(),
        SimpleNamespace(id=creator_id),
        session,
    )

    assert result is published
    repository.transition_strategy.assert_awaited_once_with(
        strategy_id=strategy_id,
        creator_id=creator_id,
        target=StrategyStatus.PUBLISHED,
    )
    session.commit.assert_not_awaited()
