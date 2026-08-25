import asyncio
import uuid

import pytest
from app.bootstrap.instruments import SYNTHETIC_EQUITY_ID
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.models.execution import ExecutionIntent, ExecutionStatus
from app.models.strategy import Strategy, StrategyStatus
from app.models.user import Role, user_roles
from tests.test_allocations import create_allocation, create_deployed_strategy
from tests.test_backtest_execution import (
    client,
    create_strategy_version,
    register_and_login,
)


EXECUTION_INTENTS_PATH = "/api/v1/execution-intents"


def execution_intents_path(allocation_id: str) -> str:
    return f"/api/v1/allocations/{allocation_id}/execution-intents"


async def create_eligible_allocation(client, slug: str):
    creator_headers = await register_and_login(client)
    investor_headers = await register_and_login(client, enroll=False)
    strategy, version = await create_deployed_strategy(client, creator_headers, slug)
    response = await create_allocation(client, investor_headers, strategy["id"])
    assert response.status_code == 201
    return creator_headers, investor_headers, strategy, version, response.json()


@pytest.mark.asyncio
async def test_investor_creates_persisted_pending_paper_intent_with_snapshots(client):
    creator_headers, investor_headers, strategy, version, allocation = (
        await create_eligible_allocation(client, "execution-create")
    )

    response = await client.post(
        execution_intents_path(allocation["id"]),
        headers=investor_headers,
        json={"idempotency_key": "request-1"},
    )
    assert response.status_code == 201
    intent = response.json()
    assert intent["allocation_intent_id"] == allocation["id"]
    assert intent["strategy_id"] == strategy["id"]
    assert intent["strategy_version_id"] == version["id"]
    assert intent["strategy_name"] == strategy["name"]
    assert intent["strategy_version_number"] == version["version_number"]
    assert intent["instrument_id"] == str(SYNTHETIC_EQUITY_ID)
    assert intent["instrument_snapshot"] == {
        "canonical_symbol": "TRADEEBH_TEST_EQ",
        "exchange_symbol": "TRADEEBH_TEST_EQ",
        "name": "TradeEBH Synthetic Reference Equity (not a real security)",
        "exchange_code": "NSE",
        "instrument_type": "equity",
        "quote_currency": "INR",
        "tick_size": "0.01",
        "lot_size": 1,
        "is_tradeable": True,
    }
    assert intent["notional_amount_snapshot"] == "1000.50000000"
    assert intent["currency_snapshot"] == "USD"
    assert intent["mode"] == "paper"
    assert intent["status"] == "pending"
    assert intent["idempotency_key"] == "request-1"
    assert intent["started_at"] is None
    assert intent["completed_at"] is None
    assert intent["error_code"] is None
    assert intent["error_message"] is None

    response = await client.patch(
        f"/api/v1/allocations/{allocation['id']}",
        headers=investor_headers,
        json={"notional_amount": "2500.25", "currency": "eur"},
    )
    assert response.status_code == 200
    response = await client.get(
        f"{EXECUTION_INTENTS_PATH}/{intent['id']}", headers=investor_headers
    )
    assert response.status_code == 200
    assert response.json()["notional_amount_snapshot"] == "1000.50000000"
    assert response.json()["currency_snapshot"] == "USD"

    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=creator_headers,
        json={"instrument_id": str(SYNTHETIC_EQUITY_ID), "configuration": {}, "backtest_configuration": {}},
    )
    assert response.status_code == 201
    newer_version = response.json()
    async with AsyncSessionLocal() as session:
        persisted_strategy = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )
        assert persisted_strategy is not None
        persisted_strategy.current_version_id = uuid.UUID(newer_version["id"])
        await session.commit()

    response = await client.get(
        f"{EXECUTION_INTENTS_PATH}/{intent['id']}", headers=investor_headers
    )
    assert response.status_code == 200
    assert response.json()["strategy_version_id"] == version["id"]
    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(ExecutionIntent).where(ExecutionIntent.id == uuid.UUID(intent["id"]))
        )
    assert persisted is not None
    assert persisted.status == ExecutionStatus.PENDING
    assert persisted.strategy_version_id == uuid.UUID(version["id"])


@pytest.mark.asyncio
async def test_execution_creation_requires_still_deployed_public_strategy(client):
    creator_headers, investor_headers, strategy, _, allocation = (
        await create_eligible_allocation(client, "execution-eligibility")
    )
    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(strategy["id"]))
        )
        assert persisted is not None
        persisted.status = StrategyStatus.PUBLISHED
        await session.commit()
    response = await client.post(
        execution_intents_path(allocation["id"]), headers=investor_headers, json={}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "Strategy is not eligible for execution"}

    archived_strategy, _ = await create_deployed_strategy(
        client, creator_headers, "execution-archived"
    )
    response = await create_allocation(
        client, investor_headers, archived_strategy["id"]
    )
    assert response.status_code == 201
    archived_allocation = response.json()
    response = await client.post(
        f"/api/v1/strategies/{archived_strategy['id']}/archive", headers=creator_headers
    )
    assert response.status_code == 200
    response = await client.post(
        execution_intents_path(archived_allocation["id"]),
        headers=investor_headers,
        json={},
    )
    assert response.status_code == 409

    _, private_investor_headers, private_strategy, _, private_allocation = (
        await create_eligible_allocation(client, "execution-private")
    )
    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Strategy).where(Strategy.id == uuid.UUID(private_strategy["id"]))
        )
        assert persisted is not None
        persisted.is_public = False
        await session.commit()
    response = await client.post(
        execution_intents_path(private_allocation["id"]),
        headers=private_investor_headers,
        json={},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_execution_intent_list_get_and_ownership_hiding(client):
    _, investor_headers, _, _, allocation = await create_eligible_allocation(
        client, "execution-list"
    )
    other_investor_headers = await register_and_login(client, enroll=False)
    response = await client.post(
        execution_intents_path(allocation["id"]), headers=investor_headers, json={}
    )
    assert response.status_code == 201
    intent = response.json()

    response = await client.get(EXECUTION_INTENTS_PATH, headers=investor_headers)
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [intent["id"]]
    response = await client.get(
        f"{EXECUTION_INTENTS_PATH}/{intent['id']}", headers=investor_headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == intent["id"]

    response = await client.post(
        execution_intents_path(allocation["id"]), headers=other_investor_headers, json={}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Allocation not found"}
    response = await client.get(
        f"{EXECUTION_INTENTS_PATH}/{intent['id']}", headers=other_investor_headers
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Execution intent not found"}
    response = await client.get(EXECUTION_INTENTS_PATH, headers=other_investor_headers)
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_execution_intent_requires_investor_and_rejects_client_controlled_fields(client):
    _, investor_headers, _, _, allocation = await create_eligible_allocation(
        client, "execution-access"
    )
    path = execution_intents_path(allocation["id"])
    assert (await client.post(path, json={})).status_code == 401
    assert (await client.get(EXECUTION_INTENTS_PATH)).status_code == 401
    assert (await client.get(f"{EXECUTION_INTENTS_PATH}/{uuid.uuid4()}")).status_code == 401

    creator_only_headers = await register_and_login(client)
    me_response = await client.get("/api/v1/auth/me", headers=creator_only_headers)
    creator_only_id = uuid.UUID(me_response.json()["id"])
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
    response = await client.get(EXECUTION_INTENTS_PATH, headers=creator_only_headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "Investor role is required"}
    assert (await client.post(path, headers=creator_only_headers, json={})).status_code == 403

    response = await client.post(
        path,
        headers=investor_headers,
        json={
            "mode": "live",
            "status": "completed",
            "investor_user_id": str(uuid.uuid4()),
            "strategy_version_id": str(uuid.uuid4()),
            "error_message": "client supplied",
            "started_at": "2026-01-01T00:00:00Z",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_execution_intent_idempotency_and_active_constraint(client):
    _, investor_headers, strategy, _, allocation = await create_eligible_allocation(
        client, "execution-idempotency"
    )
    path = execution_intents_path(allocation["id"])
    response = await client.post(
        path, headers=investor_headers, json={"idempotency_key": "repeatable-key"}
    )
    assert response.status_code == 201
    first = response.json()
    response = await client.post(
        path, headers=investor_headers, json={"idempotency_key": "repeatable-key"}
    )
    assert response.status_code == 200
    assert response.json()["id"] == first["id"]
    response = await client.post(path, headers=investor_headers, json={})
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Allocation already has an active execution intent"
    }

    response = await create_allocation(client, investor_headers, strategy["id"], amount="2000")
    assert response.status_code == 201
    other_allocation = response.json()
    response = await client.post(
        execution_intents_path(other_allocation["id"]),
        headers=investor_headers,
        json={"idempotency_key": "repeatable-key"},
    )
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Idempotency key is already associated with another allocation"
    }

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(ExecutionIntent).where(ExecutionIntent.id == uuid.UUID(first["id"]))
        )
        assert persisted is not None
        persisted.status = ExecutionStatus.COMPLETED
        await session.commit()
    response = await client.post(path, headers=investor_headers, json={})
    assert response.status_code == 201
    assert response.json()["status"] == "pending"

    async with AsyncSessionLocal() as session:
        first_persisted = await session.scalar(
            select(ExecutionIntent).where(ExecutionIntent.id == uuid.UUID(first["id"]))
        )
        assert first_persisted is not None
        duplicate = ExecutionIntent(
            allocation_intent_id=first_persisted.allocation_intent_id,
            investor_user_id=first_persisted.investor_user_id,
            strategy_id=first_persisted.strategy_id,
            strategy_version_id=first_persisted.strategy_version_id,
            notional_amount_snapshot=first_persisted.notional_amount_snapshot,
            currency_snapshot=first_persisted.currency_snapshot,
            mode="paper",
            status=ExecutionStatus.PENDING,
        )
        session.add(duplicate)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_allocation_delete_and_intent_creation_are_serialized(client):
    _, investor_headers, _, _, allocation = await create_eligible_allocation(
        client, "allocation-delete-race"
    )
    allocation_path = f"/api/v1/allocations/{allocation['id']}"

    create_response, delete_response = await asyncio.gather(
        client.post(execution_intents_path(allocation["id"]), headers=investor_headers, json={}),
        client.delete(allocation_path, headers=investor_headers),
    )

    assert (create_response.status_code, delete_response.status_code) in {
        (201, 409),
        (404, 204),
    }
    if create_response.status_code == 201:
        assert delete_response.json() == {
            "detail": "Allocation with execution intents cannot be deleted"
        }
