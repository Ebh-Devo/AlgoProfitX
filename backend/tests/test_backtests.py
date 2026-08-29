import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.backtest import Backtest
from app.models.strategy import StrategyVersion
from app.models.instrument import Instrument
from app.bootstrap.instruments import SYNTHETIC_EQUITY_ID


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


def unique_email() -> str:
    return f"backtest-{uuid.uuid4().hex}@example.com"


async def register_and_login(
    client: AsyncClient,
    enroll: bool = True,
) -> tuple[dict[str, str], dict[str, object]]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "TestPassword123"},
    )
    assert response.status_code == 201
    registered = response.json()

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": registered["email"], "password": "TestPassword123"},
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    if enroll:
        response = await client.post(
            "/api/v1/auth/creator/enroll",
            headers=headers,
        )
        assert response.status_code == 200

    return headers, registered


async def create_strategy_version(
    client: AsyncClient,
    headers: dict[str, str],
    slug: str,
) -> tuple[dict[str, object], dict[str, object]]:
    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json={"name": f"Backtest {slug}", "slug": slug},
    )
    assert response.status_code == 201
    strategy = response.json()

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "instrument_id": str(SYNTHETIC_EQUITY_ID),
            "configuration": {
                "instrument": "TRADEEBH_TEST_EQ",
                "entry": {"fast_period": 20},
            },
            "backtest_configuration": {
                "initial_capital": 100000,
                "fees": {"commission": 20},
                "timeframe": "1h",
                "start_date": "2026-01-01T00:00:00Z",
                "end_date": "2026-02-01T00:00:00Z",
                "adjustment_policy": "unadjusted",
            },
        },
    )
    assert response.status_code == 201
    return strategy, response.json()


def backtests_path(strategy_id: str, version_id: str) -> str:
    return f"/api/v1/strategies/{strategy_id}/versions/{version_id}/backtests"


@pytest.mark.asyncio
async def test_creator_creates_queued_backtest_with_independent_snapshots(client):
    headers, registered = await register_and_login(client)
    strategy, version = await create_strategy_version(
        client,
        headers,
        "backtest-create",
    )

    response = await client.post(
        backtests_path(strategy["id"], version["id"]),
        headers=headers,
        json={
            "market_data_reference": "future-data-snapshot",
            "market_data_provider": "client-injected",
            "dataset_reference": "client-dataset",
            "data_fetched_at": "2026-01-01T00:00:00Z",
            "market_data_provenance": {"trusted": False},
            "status": "completed",
            "requested_by_user_id": str(uuid.uuid4()),
            "result_summary": {"total_return": 99},
            "error_message": "injected",
            "started_at": "2026-01-01T00:00:00Z",
            "completed_at": "2026-01-02T00:00:00Z",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["strategy_version_id"] == version["id"]
    assert created["requested_by_user_id"] == registered["id"]
    assert created["status"] == "queued"
    assert created["configuration_snapshot"] == version["configuration"]
    assert (
        created["backtest_configuration_snapshot"]
        == version["backtest_configuration"]
    )
    assert created["market_data_reference"] == "future-data-snapshot"
    assert created["instrument_id"] == str(SYNTHETIC_EQUITY_ID)
    assert created["instrument_snapshot"]["canonical_symbol"] == "ALGOPROFITX_TEST_EQ"
    assert created["instrument_snapshot"]["exchange_code"] == "NSE"
    assert created["market_data_provider"] is None
    assert created["dataset_reference"] is None
    assert created["data_fetched_at"] is None
    assert created["market_data_provenance"] is None
    assert created["timeframe"] == "1h"
    assert created["adjustment_policy"] == "unadjusted"
    assert created["range_start"] == "2026-01-01T00:00:00Z"
    assert created["range_end"] == "2026-02-01T00:00:00Z"
    assert created["result_summary"] is None
    assert created["error_message"] is None
    assert created["created_at"] is not None
    assert created["started_at"] is None
    assert created["completed_at"] is None

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Backtest).where(Backtest.id == uuid.UUID(created["id"]))
        )
        version_record = await session.scalar(
            select(StrategyVersion).where(
                StrategyVersion.id == uuid.UUID(version["id"])
            )
        )
        assert persisted is not None
        assert version_record is not None
        version_record.configuration = {"instrument": "MUTATED"}
        version_record.backtest_configuration = {"initial_capital": 1}
        instrument_record = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        assert instrument_record is not None
        instrument_record.name = "Mutated Instrument Name"
        instrument_record.exchange_symbol = "MUTATED"
        await session.commit()

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Backtest).where(Backtest.id == uuid.UUID(created["id"]))
        )

    assert persisted is not None
    assert persisted.configuration_snapshot == version["configuration"]
    assert persisted.backtest_configuration_snapshot == version["backtest_configuration"]
    assert persisted.instrument_snapshot == created["instrument_snapshot"]


@pytest.mark.asyncio
async def test_strategy_with_backtest_history_cannot_be_deleted(client):
    headers, _ = await register_and_login(client)
    strategy, version = await create_strategy_version(
        client, headers, "backtest-retention"
    )
    created = await client.post(
        backtests_path(strategy["id"], version["id"]),
        headers=headers,
        json={"market_data_reference": "retained-history"},
    )
    assert created.status_code == 201

    deleted = await client.delete(
        f"/api/v1/strategies/{strategy['id']}", headers=headers
    )
    assert deleted.status_code == 409
    assert deleted.json() == {
        "detail": "Strategy with historical records cannot be deleted"
    }

    async with AsyncSessionLocal() as session:
        assert await session.get(Backtest, uuid.UUID(created.json()["id"])) is not None
        assert await session.get(
            StrategyVersion, uuid.UUID(version["id"])
        ) is not None
@pytest.mark.asyncio
async def test_backtest_provenance_constraints_and_instrument_fk_are_restrictive(client):
    headers, _ = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "backtest-integrity")
    response = await client.post(
        backtests_path(strategy["id"], version["id"]), headers=headers, json={}
    )
    assert response.status_code == 201
    backtest_id = uuid.UUID(response.json()["id"])

    async with AsyncSessionLocal() as session:
        backtest = await session.get(Backtest, backtest_id)
        assert backtest is not None
        backtest.market_data_provenance = []
        with pytest.raises(IntegrityError):
            await session.commit()

    async with AsyncSessionLocal() as session:
        backtest = await session.get(Backtest, backtest_id)
        assert backtest is not None
        backtest.market_data_provenance = {"payload": "x" * 9000}
        with pytest.raises(IntegrityError):
            await session.commit()

    async with AsyncSessionLocal() as session:
        version_record = await session.get(StrategyVersion, uuid.UUID(version["id"]))
        assert version_record is not None
        version_record.instrument_id = None
        await session.commit()
    async with AsyncSessionLocal() as session:
        instrument_record = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        assert instrument_record is not None
        await session.delete(instrument_record)
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_multiple_backtests_list_get_and_paginate_deterministically(client):
    headers, _ = await register_and_login(client)
    strategy, version = await create_strategy_version(
        client,
        headers,
        "backtest-list",
    )
    path = backtests_path(strategy["id"], version["id"])

    created = []
    for market_data_reference in ("first", "second", "third"):
        response = await client.post(
            path,
            headers=headers,
            json={"market_data_reference": market_data_reference},
        )
        assert response.status_code == 201
        created.append(response.json())

    async with AsyncSessionLocal() as session:
        for day, backtest in enumerate(created, start=1):
            persisted = await session.scalar(
                select(Backtest).where(Backtest.id == uuid.UUID(backtest["id"]))
            )
            assert persisted is not None
            persisted.created_at = datetime(2026, 1, day, tzinfo=timezone.utc)
        await session.commit()

    all_response = await client.get(path, headers=headers)
    first_page = await client.get(f"{path}?limit=2&offset=0", headers=headers)
    second_page = await client.get(f"{path}?limit=2&offset=2", headers=headers)
    get_response = await client.get(
        f"{path}/{created[1]['id']}",
        headers=headers,
    )

    assert all_response.status_code == 200
    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert get_response.status_code == 200
    all_backtests = all_response.json()
    assert {backtest["id"] for backtest in all_backtests} == {
        backtest["id"] for backtest in created
    }
    assert [backtest["id"] for backtest in all_backtests] == [
        created[2]["id"],
        created[1]["id"],
        created[0]["id"],
    ]
    assert all_backtests == (
        await client.get(path, headers=headers)
    ).json()
    assert first_page.json() == all_backtests[:2]
    assert second_page.json() == all_backtests[2:]
    assert get_response.json()["id"] == created[1]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "get"])
async def test_backtest_create_and_list_require_authentication(client, method):
    path = backtests_path(
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    )
    request_kwargs = {"json": {}} if method == "post" else {}
    response = await getattr(client, method)(path, **request_kwargs)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_backtest_get_requires_authentication(client):
    response = await client.get(
        f"{backtests_path('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002')}/00000000-0000-0000-0000-000000000003"
    )

    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "get"])
async def test_investor_cannot_create_or_list_backtests(client, method):
    headers, _ = await register_and_login(client, enroll=False)
    path = backtests_path(
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    )
    request_kwargs = {"headers": headers}
    if method == "post":
        request_kwargs["json"] = {}
    response = await getattr(client, method)(path, **request_kwargs)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_investor_cannot_get_backtest(client):
    headers, _ = await register_and_login(client, enroll=False)
    response = await client.get(
        f"{backtests_path('00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002')}/00000000-0000-0000-0000-000000000003",
        headers=headers,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_owner_creator_and_missing_resources_are_hidden(client):
    owner_headers, _ = await register_and_login(client)
    other_headers, _ = await register_and_login(client)
    strategy, version = await create_strategy_version(
        client,
        owner_headers,
        "backtest-owner",
    )
    path = backtests_path(strategy["id"], version["id"])
    response = await client.post(path, headers=owner_headers, json={})
    assert response.status_code == 201
    backtest_id = response.json()["id"]

    response = await client.post(path, headers=other_headers, json={})
    assert response.status_code == 404
    assert response.json() == {"detail": "Strategy not found"}

    for endpoint in (path, f"{path}/{backtest_id}"):
        response = await client.get(endpoint, headers=other_headers)
        assert response.status_code == 404
        assert response.json() == {"detail": "Strategy not found"}

    missing_strategy_path = backtests_path(
        "00000000-0000-0000-0000-000000000001",
        version["id"],
    )
    response = await client.post(
        missing_strategy_path,
        headers=owner_headers,
        json={},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Strategy not found"}

    missing_version_path = backtests_path(
        strategy["id"],
        "00000000-0000-0000-0000-000000000002",
    )
    response = await client.get(missing_version_path, headers=owner_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Strategy version not found"}

    response = await client.get(
        f"{path}/00000000-0000-0000-0000-000000000003",
        headers=owner_headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Backtest not found"}
