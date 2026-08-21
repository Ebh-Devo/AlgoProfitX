import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.backtest import Backtest
from app.models.strategy import StrategyVersion


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
            "configuration": {
                "instrument": "XAUUSD",
                "entry": {"fast_period": 20},
            },
            "backtest_configuration": {
                "initial_capital": 100000,
                "fees": {"commission": 20},
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
        await session.commit()

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Backtest).where(Backtest.id == uuid.UUID(created["id"]))
        )

    assert persisted is not None
    assert persisted.configuration_snapshot == version["configuration"]
    assert persisted.backtest_configuration_snapshot == version["backtest_configuration"]


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
