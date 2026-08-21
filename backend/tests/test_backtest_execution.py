import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.backtest import Backtest, BacktestStatus
from app.services.backtest import _claim_queued_backtest


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client


def unique_email() -> str:
    return f"backtest-execution-{uuid.uuid4().hex}@example.com"


async def register_and_login(
    client: AsyncClient,
    enroll: bool = True,
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": unique_email(), "password": "TestPassword123"},
    )
    assert response.status_code == 201

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": response.json()["email"], "password": "TestPassword123"},
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    if enroll:
        response = await client.post(
            "/api/v1/auth/creator/enroll",
            headers=headers,
        )
        assert response.status_code == 200
    return headers


async def create_strategy_version(
    client: AsyncClient,
    headers: dict[str, str],
    slug: str,
    configuration: dict | None = None,
) -> tuple[dict, dict]:
    response = await client.post(
        "/api/v1/strategies",
        headers=headers,
        json={"name": f"Execution {slug}", "slug": slug},
    )
    assert response.status_code == 201
    strategy = response.json()
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "configuration": configuration
            or {
                "instrument": "XAUUSD",
                "entry": {
                    "type": "ema_crossover",
                    "fast_period": 3,
                    "slow_period": 5,
                },
            },
            "backtest_configuration": {
                "initial_capital": "1000",
                "start_date": "2025-01-01T00:00:00Z",
            },
        },
    )
    assert response.status_code == 201
    return strategy, response.json()


def backtests_path(strategy: dict, version: dict) -> str:
    return f"/api/v1/strategies/{strategy['id']}/versions/{version['id']}/backtests"


async def create_backtest(
    client: AsyncClient,
    headers: dict[str, str],
    strategy: dict,
    version: dict,
) -> dict:
    response = await client.post(
        backtests_path(strategy, version),
        headers=headers,
        json={},
    )
    assert response.status_code == 201
    return response.json()


def execute_path(strategy: dict, version: dict, backtest: dict) -> str:
    return f"{backtests_path(strategy, version)}/{backtest['id']}/execute"


@pytest.mark.asyncio
async def test_execute_claims_queued_backtest_then_completes_with_bounded_result(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "execute-success")
    backtest = await create_backtest(client, headers, strategy, version)

    async with AsyncSessionLocal() as session:
        claimed = await _claim_queued_backtest(session, uuid.UUID(backtest["id"]))
        assert claimed.status == BacktestStatus.RUNNING
        assert claimed.started_at is not None
        assert claimed.started_at.tzinfo is not None

    response = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Backtest cannot execute while running"}

    # A second queued attempt exercises the successful endpoint path.
    backtest = await create_backtest(client, headers, strategy, version)
    response = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 200
    completed = response.json()
    assert completed["status"] == "completed"
    assert completed["started_at"] is not None
    assert completed["completed_at"] is not None
    assert completed["error_message"] is None
    assert completed["result_summary"]["initial_capital"] == "1000.00000000"
    assert completed["result_summary"]["trade_count"] == 1
    assert completed["result_summary"]["engine_identifier"] == "ema-crossover-reference-v1"
    assert completed["result_summary"]["provider_identifier"] == "synthetic-local-v1"
    assert len(completed["result_summary"]["trades"]) <= 100
    assert len(completed["result_summary"]["equity_curve"]) <= 256

    async with AsyncSessionLocal() as session:
        persisted = await session.scalar(
            select(Backtest).where(Backtest.id == uuid.UUID(backtest["id"]))
        )
    assert persisted is not None
    assert persisted.status == BacktestStatus.COMPLETED
    assert persisted.result_summary == completed["result_summary"]


@pytest.mark.asyncio
async def test_execution_result_is_deterministic_and_terminal_attempts_conflict(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, headers, "execute-deterministic")
    first = await create_backtest(client, headers, strategy, version)
    second = await create_backtest(client, headers, strategy, version)

    first_response = await client.post(execute_path(strategy, version, first), headers=headers)
    second_response = await client.post(execute_path(strategy, version, second), headers=headers)
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_response.json()["result_summary"] == second_response.json()["result_summary"]

    response = await client.post(execute_path(strategy, version, first), headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Backtest cannot execute while completed"}


@pytest.mark.asyncio
async def test_engine_failure_is_sanitized_persisted_and_terminal(client):
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(
        client,
        headers,
        "execute-failure",
        configuration={"entry": {"type": "unsupported"}},
    )
    backtest = await create_backtest(client, headers, strategy, version)

    response = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 200
    failed = response.json()
    assert failed["status"] == "failed"
    assert failed["started_at"] is not None
    assert failed["completed_at"] is not None
    assert failed["result_summary"] is None
    assert (
        failed["error_message"]
        == "Reference engine supports only entry.type=ema_crossover"
    )
    assert "\n" not in failed["error_message"]
    assert len(failed["error_message"]) <= 500

    response = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert response.status_code == 409
    assert response.json() == {"detail": "Backtest cannot execute while failed"}


@pytest.mark.asyncio
async def test_execution_requires_creator_authentication_and_ownership(client):
    owner_headers = await register_and_login(client)
    investor_headers = await register_and_login(client, enroll=False)
    other_creator_headers = await register_and_login(client)
    strategy, version = await create_strategy_version(client, owner_headers, "execute-access")
    backtest = await create_backtest(client, owner_headers, strategy, version)
    path = execute_path(strategy, version, backtest)

    assert (await client.post(path)).status_code == 401
    assert (await client.post(path, headers=investor_headers)).status_code == 403
    response = await client.post(path, headers=other_creator_headers)
    assert response.status_code == 404
    assert response.json() == {"detail": "Strategy not found"}


@pytest.mark.asyncio
async def test_execution_hides_backtest_version_mismatch(client):
    headers = await register_and_login(client)
    strategy, first_version = await create_strategy_version(client, headers, "execute-mismatch")
    backtest = await create_backtest(client, headers, strategy, first_version)
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "configuration": {
                "entry": {
                    "type": "ema_crossover",
                    "fast_period": 3,
                    "slow_period": 5,
                }
            },
            "backtest_configuration": {"initial_capital": "1000"},
        },
    )
    assert response.status_code == 201
    second_version = response.json()

    response = await client.post(
        execute_path(strategy, second_version, backtest),
        headers=headers,
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Backtest not found"}
