"""End-to-end HTTP parity: the real app on the Catalyst provider, backed by an in-memory Data Store.

These reuse the request helpers of the PostgreSQL contract tests (registration, strategies, versions,
backtests, V2), so the Catalyst provider is exercised through the same API calls. Nothing here
touches a live Catalyst environment.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.bootstrap.instruments import SYNTHETIC_EQUITY_ID
from app.core.abuse import abuse_controller
from app.core.config import get_settings
from app.main import app
from app.persistence.catalyst.instrument import CatalystInstrumentRepository
from app.persistence.catalyst.schema import schema_capabilities
from tests.catalyst_e2e import full_store, route_all_catalyst_clients_to
from tests.test_backtest_execution import (
    backtests_path,
    create_backtest,
    execute_path,
    register_and_login,
)
from tests.test_strategy_v2_api_contract import (
    VALIDATE,
    body,
    create_body,
    new_strategy,
    v2_version,
    versions_path,
)

UNSUPPORTED_CODE = "strategy_definition_version_unsupported_for_execution"


async def deploy_stack(monkeypatch, *, with_schema_column: bool):
    store = full_store(with_schema_column=with_schema_column)
    settings = get_settings()
    monkeypatch.setattr(settings, "persistence_provider", "catalyst")
    monkeypatch.setattr(settings, "backtest_execution_mode", "inline")
    route_all_catalyst_clients_to(monkeypatch, store)
    schema_capabilities.clear()  # the real probe decides, against the store's real columns
    await CatalystInstrumentRepository(store).bootstrap_defaults()
    await abuse_controller.clear()
    return store


@pytest_asyncio.fixture
async def legacy_stack(monkeypatch):
    """Tables as they exist today: no definition_schema_version column."""
    store = await deploy_stack(monkeypatch, with_schema_column=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, store


@pytest_asyncio.fixture
async def provisioned_stack(monkeypatch):
    """Tables after the proposed (not yet approved) schema change."""
    store = await deploy_stack(monkeypatch, with_schema_column=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, store


async def v1_strategy(client, headers, slug):
    response = await client.post(
        "/api/v1/strategies", headers=headers, json={"name": f"E2E {slug}", "slug": slug}
    )
    assert response.status_code == 201, response.text
    strategy = response.json()
    response = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "instrument_id": str(SYNTHETIC_EQUITY_ID),
            "configuration": {
                "instrument": "ALGOPROFITX_TEST_EQ",
                "entry": {"type": "ema_crossover", "fast_period": 5, "slow_period": 20},
            },
            "backtest_configuration": {"initial_capital": "100000", "timeframe": "1d"},
        },
    )
    assert response.status_code == 201, response.text
    return strategy, response.json()


# ---------------------------------------------------------------------------- V1 end to end


@pytest.mark.asyncio
async def test_v1_lifecycle_creator_to_investor_paper_execution(legacy_stack):
    client, store = legacy_stack
    creator = await register_and_login(client)
    strategy, version = await v1_strategy(client, creator, "e2e-v1")
    assert version["definition_schema_version"] == 1 and version["version_number"] == 1

    # Backtest: queue, execute inline, read back, analytics.
    backtest = await create_backtest(client, creator, strategy, version)
    assert backtest["status"] == "queued" and backtest["definition_schema_version"] == 1
    executed = await client.post(execute_path(strategy, version, backtest), headers=creator)
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "completed"
    assert executed.json()["result_summary"]["engine_identifier"] == "ema-crossover-reference-v1"
    again = await client.post(execute_path(strategy, version, backtest), headers=creator)
    assert again.status_code == 409  # exactly-once claim: a finished backtest cannot be re-run
    listed = await client.get(backtests_path(strategy, version), headers=creator)
    assert listed.status_code == 200 and [item["id"] for item in listed.json()] == [backtest["id"]]
    analytics = await client.get(
        f"{backtests_path(strategy, version)}/{backtest['id']}/analytics", headers=creator
    )
    assert analytics.status_code == 200 and analytics.json()["backtest_id"] == backtest["id"]

    # Lifecycle: publish -> marketplace -> deploy.
    assert (await client.post(f"/api/v1/strategies/{strategy['id']}/publish", headers=creator)).status_code == 200
    marketplace = await client.get("/api/v1/marketplace/strategies")
    assert marketplace.status_code == 200 and strategy["id"] in [item["id"] for item in marketplace.json()]
    assert (await client.post(f"/api/v1/strategies/{strategy['id']}/deploy", headers=creator)).status_code == 200

    # An investor allocates and runs a paper execution, with idempotency.
    investor = await register_and_login(client, enroll=False)
    allocation = await client.post(
        "/api/v1/allocations",
        headers=investor,
        json={"strategy_id": strategy["id"], "notional_amount": "1000.50", "currency": "INR"},
    )
    assert allocation.status_code == 201, allocation.text
    allocation_id = allocation.json()["id"]
    path = f"/api/v1/allocations/{allocation_id}/execution-intents"
    first = await client.post(path, headers=investor, json={"idempotency_key": "e2e-key-0001"})
    assert first.status_code == 201, first.text
    replay = await client.post(path, headers=investor, json={"idempotency_key": "e2e-key-0001"})
    assert replay.status_code == 200 and replay.json()["id"] == first.json()["id"]
    ran = await client.post(f"/api/v1/execution-intents/{first.json()['id']}/execute", headers=investor)
    assert ran.status_code == 200, ran.text
    assert ran.json()["status"] == "completed" and ran.json()["paper_result_summary"] is not None

    # Ownership: another investor cannot see or use it.
    stranger = await register_and_login(client, enroll=False)
    assert (await client.get(f"/api/v1/allocations/{allocation_id}", headers=stranger)).status_code == 404

    # Real table uniqueness held: one version row, one strategy lock released.
    assert len(store.rows["AlgoProfitXStrategyVersions"]) == 1
    assert store.rows["AlgoProfitXStrategyLocks"] == []


@pytest.mark.asyncio
async def test_duplicate_slug_and_version_numbers_are_enforced_through_http(legacy_stack):
    client, _ = legacy_stack
    headers = await register_and_login(client)
    strategy, first = await v1_strategy(client, headers, "e2e-dup")
    again = await client.post(
        "/api/v1/strategies", headers=headers, json={"name": "Another", "slug": "e2e-dup"}
    )
    assert again.status_code in (409, 422)
    second = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "instrument_id": str(SYNTHETIC_EQUITY_ID),
            "configuration": {"instrument": "ALGOPROFITX_TEST_EQ", "entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 9}},
            "backtest_configuration": {"initial_capital": "1000", "timeframe": "1d"},
        },
    )
    assert second.status_code == 201 and second.json()["version_number"] == 2


# ---------------------------------------------------------------------- V2 fail-closed (today)


@pytest.mark.asyncio
async def test_v2_is_refused_cleanly_while_the_column_is_not_provisioned(legacy_stack):
    client, store = legacy_stack
    headers = await register_and_login(client)
    strategy = await new_strategy(client, headers, "e2e-v2-closed")
    response = await client.post(versions_path(strategy), headers=headers, json=create_body())
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["code"] == "strategy_definition_v2_storage_unavailable"
    assert "AlgoProfitX" not in response.text  # no internal table names leak
    assert store.rows["AlgoProfitXStrategyVersions"] == []  # nothing stored, never as V1
    # V1 on the same strategy still works and validation (no persistence) still answers.
    ok = await client.post(
        f"/api/v1/strategies/{strategy['id']}/versions",
        headers=headers,
        json={
            "instrument_id": str(SYNTHETIC_EQUITY_ID),
            "configuration": {"instrument": "ALGOPROFITX_TEST_EQ", "entry": {"type": "ema_crossover", "fast_period": 5, "slow_period": 20}},
            "backtest_configuration": {"initial_capital": "1000", "timeframe": "1d"},
        },
    )
    assert ok.status_code == 201
    validated = await client.post(VALIDATE, headers=headers, json=body())
    assert validated.status_code == 200 and validated.json()["valid"] is True


# ------------------------------------------------------- V2 after the (proposed) schema change


@pytest.mark.asyncio
async def test_v2_works_end_to_end_once_the_column_exists(provisioned_stack):
    client, store = provisioned_stack
    headers = await register_and_login(client)
    strategy, version = await v2_version(client, headers, "e2e-v2-open")
    assert version["definition_schema_version"] == 2
    assert store.rows["AlgoProfitXStrategyVersions"][0]["definition_schema_version"] == 2

    backtest = await create_backtest(client, headers, strategy, version)
    assert backtest["definition_schema_version"] == 2
    executed = await client.post(execute_path(strategy, version, backtest), headers=headers)
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "completed"
    assert executed.json()["result_summary"]["engine_identifier"] != "ema-crossover-reference-v1"

    # V2 is backtest-only: publish and deploy are refused with the structured contract.
    published = await client.post(f"/api/v1/strategies/{strategy['id']}/publish", headers=headers)
    assert published.status_code == 409 and published.json()["detail"]["code"] == UNSUPPORTED_CODE
    row = store.rows["AlgoProfitXStrategies"][0]
    assert row["status"] == "draft" and not row["is_public"]
    assert store.rows["AlgoProfitXStrategyLocks"] == []  # the refusal released its lock

    # A V1 version still coexists and lists with the right markers.
    _, v1 = await v1_strategy(client, headers, "e2e-v1-coexists")
    assert v1["definition_schema_version"] == 1
    versions = await client.get(f"/api/v1/strategies/{strategy['id']}/versions", headers=headers)
    assert [item["definition_schema_version"] for item in versions.json()] == [2]


# --------------------------------------------------------------------------- auth over HTTP


@pytest.mark.asyncio
async def test_auth_session_lifecycle_over_http_on_the_catalyst_provider(legacy_stack):
    client, store = legacy_stack
    settings = get_settings()
    email = f"e2e-{uuid.uuid4().hex}@example.com"
    assert (await client.post("/api/v1/auth/register", json={"email": email, "password": "TestPassword123"})).status_code == 201
    assert (await client.post("/api/v1/auth/register", json={"email": email.upper(), "password": "TestPassword123"})).status_code == 409
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "TestPassword123"})
    assert login.status_code == 200
    csrf = client.cookies[settings.auth_csrf_cookie_name]
    rotated = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert rotated.status_code == 200
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {rotated.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == email
    # Only the hash of the refresh token is stored, never the token.
    stored = store.rows["AlgoProfitXAuthSessions"][0]
    assert client.cookies[settings.auth_refresh_cookie_name] not in str(stored.values())
    out = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": client.cookies.get(settings.auth_csrf_cookie_name, csrf)})
    assert out.status_code == 204
    assert store.rows["AlgoProfitXAuthSessions"][0]["revoked_at"] is not None
