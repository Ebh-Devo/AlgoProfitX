import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.allocation import AllocationIntent, AllocationStatus
from app.models.strategy import Strategy
from app.models.user import Role, user_roles
from tests.test_backtest_execution import (
    client,
    create_strategy_version,
    register_and_login,
)


ALLOCATION_PATH = "/api/v1/allocations"


async def create_deployed_strategy(client, headers: dict[str, str], slug: str) -> tuple[dict, dict]:
    strategy, version = await create_strategy_version(client, headers, slug)
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/publish",
        headers=headers,
    )
    assert response.status_code == 200
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/deploy",
        headers=headers,
    )
    assert response.status_code == 200
    return strategy, version


async def create_allocation(
    client,
    headers: dict[str, str],
    strategy_id: str,
    amount: str = "1000.5",
    currency: str = "usd",
):
    return await client.post(
        ALLOCATION_PATH,
        headers=headers,
        json={
            "strategy_id": strategy_id,
            "notional_amount": amount,
            "currency": currency,
        },
    )


@pytest.mark.asyncio
async def test_investor_creates_persisted_allocation_pinned_to_current_version(client):
    owner_headers = await register_and_login(client)
    investor_headers = await register_and_login(client)
    strategy, first_version = await create_deployed_strategy(
        client,
        owner_headers,
        "allocation-pin",
    )

    response = await create_allocation(client, investor_headers, strategy["id"])
    assert response.status_code == 201
    allocation = response.json()
    assert allocation["strategy_id"] == strategy["id"]
    assert allocation["strategy_version_id"] == first_version["id"]
    assert allocation["strategy_name"] == strategy["name"]
    assert allocation["strategy_version_number"] == first_version["version_number"]
    assert allocation["notional_amount"] == "1000.50000000"
    assert allocation["currency"] == "USD"
    assert allocation["status"] == "active"

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=owner_headers,
        json={"configuration": {}, "backtest_configuration": {}},
    )
    assert response.status_code == 201
    second_version = response.json()
    async with AsyncSessionLocal() as session:
        persisted_strategy = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )
        assert persisted_strategy is not None
        persisted_strategy.current_version_id = uuid.UUID(second_version["id"])
        await session.commit()

    response = await client.get(
        f"{ALLOCATION_PATH}/{allocation['id']}",
        headers=investor_headers,
    )
    assert response.status_code == 200
    assert response.json()["strategy_version_id"] == first_version["id"]
    assert response.json()["strategy_name"] == strategy["name"]
    assert response.json()["strategy_version_number"] == first_version["version_number"]

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(AllocationIntent).where(
                AllocationIntent.id == uuid.UUID(allocation["id"])
            )
        )
    assert persisted is not None
    assert persisted.status == AllocationStatus.ACTIVE
    assert persisted.strategy_version_id == uuid.UUID(first_version["id"])


@pytest.mark.asyncio
async def test_allocation_requires_deployed_public_strategy_with_current_version(client):
    owner_headers = await register_and_login(client)
    investor_headers = await register_and_login(client)
    strategy, _ = await create_strategy_version(client, owner_headers, "allocation-published")

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/publish",
        headers=owner_headers,
    )
    assert response.status_code == 200
    response = await create_allocation(client, investor_headers, strategy["id"])
    assert response.status_code == 409
    assert response.json() == {"detail": "Strategy is not eligible for allocation"}

    deployed_strategy, _ = await create_deployed_strategy(
        client,
        owner_headers,
        "allocation-private",
    )
    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(deployed_strategy["id"]))
        )
        assert persisted is not None
        persisted.is_public = False
        await session.commit()
    response = await create_allocation(client, investor_headers, deployed_strategy["id"])
    assert response.status_code == 409

    missing_current_strategy, _ = await create_deployed_strategy(
        client,
        owner_headers,
        "allocation-no-current",
    )
    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(
                Strategy.id == uuid.UUID(missing_current_strategy["id"])
            )
        )
        assert persisted is not None
        persisted.current_version_id = None
        await session.commit()
    response = await create_allocation(
        client,
        investor_headers,
        missing_current_strategy["id"],
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Strategy requires a current version before allocation"
    }


@pytest.mark.asyncio
async def test_allocation_validation_and_update_only_allows_amount_and_currency(client):
    owner_headers = await register_and_login(client)
    investor_headers = await register_and_login(client)
    strategy, version = await create_deployed_strategy(
        client,
        owner_headers,
        "allocation-validation",
    )

    for amount in ("0", "-1", "0.000000001", None):
        response = await create_allocation(
            client,
            investor_headers,
            strategy["id"],
            amount=amount,
        )
        assert response.status_code == 422
    for currency in ("US", "USDD", "US1", None):
        response = await create_allocation(
            client,
            investor_headers,
            strategy["id"],
            currency=currency,
        )
        assert response.status_code == 422

    response = await create_allocation(client, investor_headers, strategy["id"])
    assert response.status_code == 201
    allocation = response.json()
    response = await client.patch(
        f"{ALLOCATION_PATH}/{allocation['id']}",
        headers=investor_headers,
        json={"notional_amount": "2500.25", "currency": "eur"},
    )
    assert response.status_code == 200
    assert response.json()["notional_amount"] == "2500.25000000"
    assert response.json()["currency"] == "EUR"

    response = await client.patch(
        f"{ALLOCATION_PATH}/{allocation['id']}",
        headers=investor_headers,
        json={"strategy_id": str(uuid.uuid4()), "status": "active"},
    )
    assert response.status_code == 422
    assert version["id"] == allocation["strategy_version_id"]

    for payload in ({"notional_amount": None}, {"currency": None}):
        response = await client.patch(
            f"{ALLOCATION_PATH}/{allocation['id']}",
            headers=investor_headers,
            json=payload,
        )
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_investor_lists_gets_updates_deletes_and_can_duplicate_allocations(client):
    owner_headers = await register_and_login(client)
    investor_headers = await register_and_login(client)
    other_investor_headers = await register_and_login(client)
    strategy, version = await create_deployed_strategy(
        client,
        owner_headers,
        "allocation-crud",
    )
    first_response = await create_allocation(client, investor_headers, strategy["id"])
    second_response = await create_allocation(
        client,
        investor_headers,
        strategy["id"],
        amount="2000",
    )
    other_response = await create_allocation(
        client,
        other_investor_headers,
        strategy["id"],
    )
    assert all(
        response.status_code == 201
        for response in (first_response, second_response, other_response)
    )
    first, second, other = (
        first_response.json(),
        second_response.json(),
        other_response.json(),
    )
    assert first["strategy_version_id"] == second["strategy_version_id"] == version["id"]

    response = await client.get(ALLOCATION_PATH, headers=investor_headers)
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {first["id"], second["id"]}
    response = await client.get(
        f"{ALLOCATION_PATH}/{first['id']}", headers=investor_headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]

    response = await client.delete(
        f"{ALLOCATION_PATH}/{first['id']}", headers=investor_headers
    )
    assert response.status_code == 204
    assert (
        await client.get(f"{ALLOCATION_PATH}/{first['id']}", headers=investor_headers)
    ).status_code == 404
    assert other["id"] not in {item["id"] for item in (await client.get(ALLOCATION_PATH, headers=investor_headers)).json()}


@pytest.mark.asyncio
async def test_allocation_authentication_investor_role_and_ownership(client):
    owner_headers = await register_and_login(client)
    investor_headers = await register_and_login(client)
    strategy, _ = await create_deployed_strategy(client, owner_headers, "allocation-access")
    allocation_response = await create_allocation(
        client,
        investor_headers,
        strategy["id"],
    )
    assert allocation_response.status_code == 201
    allocation = allocation_response.json()

    assert (await client.get(ALLOCATION_PATH)).status_code == 401
    assert (await client.post(ALLOCATION_PATH, json={})).status_code == 401
    for method in ("get", "patch", "delete"):
        request_kwargs = {}
        if method == "patch":
            request_kwargs["json"] = {"currency": "EUR"}
        assert (
            await getattr(client, method)(
                f"{ALLOCATION_PATH}/{allocation['id']}",
                **request_kwargs,
            )
        ).status_code == 401

    creator_only_headers = await register_and_login(client)
    me_response = await client.get("/api/v1/auth/me", headers=creator_only_headers)
    creator_only_id = uuid.UUID(me_response.json()["id"])
    await client.post("/api/v1/auth/creator/enroll", headers=creator_only_headers)
    async with AsyncSessionLocal() as session:
        investor_role = await session.scalar(select(Role).where(Role.name == "INVESTOR"))
        assert investor_role is not None
        await session.execute(
            delete(user_roles).where(
                user_roles.c.user_id == creator_only_id,
                user_roles.c.role_id == investor_role.id,
            )
        )
        await session.commit()
    response = await client.get(ALLOCATION_PATH, headers=creator_only_headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "Investor role is required"}

    response = await client.get(
        f"{ALLOCATION_PATH}/{allocation['id']}", headers=owner_headers
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Allocation not found"}
    assert (await create_allocation(client, owner_headers, strategy["id"])).status_code == 201
