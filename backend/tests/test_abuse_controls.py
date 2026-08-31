import asyncio
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.abuse import (
    AbuseController,
    ConcurrencyLimiter,
    InMemoryRateLimitStore,
    RateLimitRule,
    abuse_controller,
)
from app.core.config import get_settings
from app.main import app
from tests.test_backtest_execution import (
    backtests_path,
    create_strategy_version,
    register_and_login,
)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.mark.asyncio
async def test_limiter_allows_below_limit_rejects_with_retry_and_resets():
    clock = ManualClock()
    controller = AbuseController(InMemoryRateLimitStore(clock))
    rule = RateLimitRule("login_ip", "192.0.2.1", 2, 60)

    await controller.enforce((rule,), True)
    await controller.enforce((rule,), True)
    with pytest.raises(HTTPException) as raised:
        await controller.enforce((rule,), True)

    assert raised.value.status_code == 429
    assert raised.value.detail["error_code"] == "rate_limit_exceeded"
    assert raised.value.headers == {"Retry-After": "60"}

    clock.advance(60)
    await controller.enforce((rule,), True)


@pytest.mark.asyncio
async def test_limiter_isolates_keys_and_checks_multiple_rules_atomically():
    controller = AbuseController(InMemoryRateLimitStore(ManualClock()))
    first_ip = RateLimitRule("registration_ip", "192.0.2.1", 1, 60)
    second_ip = RateLimitRule("registration_ip", "192.0.2.2", 1, 60)
    account = RateLimitRule("login_account", "person@example.com", 1, 60)

    await controller.enforce((first_ip, account), True)
    await controller.enforce((second_ip,), True)
    with pytest.raises(HTTPException):
        await controller.enforce((second_ip, account), True)


@pytest.mark.asyncio
async def test_concurrency_guard_isolates_users_and_releases_after_success():
    limiter = ConcurrencyLimiter()

    async with limiter.slot("backtest", "user-a", 1):
        async with limiter.slot("backtest", "user-b", 1):
            with pytest.raises(HTTPException) as raised:
                async with limiter.slot("backtest", "user-a", 1):
                    pass

    assert raised.value.status_code == 429
    assert raised.value.detail["error_code"] == "concurrency_limit_exceeded"
    async with limiter.slot("backtest", "user-a", 1):
        pass


@pytest.mark.asyncio
async def test_concurrency_guard_releases_after_failure():
    limiter = ConcurrencyLimiter()

    with pytest.raises(RuntimeError, match="execution failed"):
        async with limiter.slot("backtest", "user-a", 1):
            raise RuntimeError("execution failed")

    async with limiter.slot("backtest", "user-a", 1):
        pass


@pytest.mark.asyncio
async def test_concurrency_guard_rejects_simultaneous_work():
    limiter = ConcurrencyLimiter()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def hold_slot() -> None:
        async with limiter.slot("backtest", "user-a", 1):
            entered.set()
            await release.wait()

    task = asyncio.create_task(hold_slot())
    await entered.wait()
    try:
        with pytest.raises(HTTPException):
            async with limiter.slot("backtest", "user-a", 1):
                pass
    finally:
        release.set()
        await task


def _set_limit(monkeypatch, name: str, value: int) -> None:
    monkeypatch.setenv(name, str(value))
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_registration_throttles_by_asgi_client_ip_and_isolates_ips(monkeypatch):
    _set_limit(monkeypatch, "REGISTRATION_IP_LIMIT", 1)
    first_transport = ASGITransport(app=app, client=("192.0.2.10", 1234))
    second_transport = ASGITransport(app=app, client=("192.0.2.11", 1234))

    try:
        async with AsyncClient(transport=first_transport, base_url="http://test") as first:
            response = await first.post(
                "/api/v1/auth/register",
                json={"email": f"{uuid.uuid4().hex}@example.com", "password": "TestPassword123"},
            )
            assert response.status_code == 201
            limited = await first.post(
                "/api/v1/auth/register",
                json={"email": f"{uuid.uuid4().hex}@example.com", "password": "TestPassword123"},
            )
        async with AsyncClient(transport=second_transport, base_url="http://test") as second:
            isolated = await second.post(
                "/api/v1/auth/register",
                json={"email": f"{uuid.uuid4().hex}@example.com", "password": "TestPassword123"},
            )

        assert limited.status_code == 429
        assert limited.json()["detail"]["error_code"] == "rate_limit_exceeded"
        assert int(limited.headers["retry-after"]) > 0
        assert isolated.status_code == 201
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_login_account_limit_is_uniform_for_existing_and_unknown_accounts(monkeypatch):
    _set_limit(monkeypatch, "LOGIN_ACCOUNT_LIMIT", 1)
    monkeypatch.setenv("LOGIN_IP_LIMIT", "20")
    get_settings.cache_clear()
    email = f"{uuid.uuid4().hex}@example.com"

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("192.0.2.20", 1)),
            base_url="http://test",
        ) as client:
            assert (
                await client.post(
                    "/api/v1/auth/register",
                    json={"email": email, "password": "TestPassword123"},
                )
            ).status_code == 201
            assert (
                await client.post(
                    "/api/v1/auth/login",
                    json={"email": email, "password": "wrong"},
                )
            ).status_code == 401

        async with AsyncClient(
            transport=ASGITransport(app=app, client=("192.0.2.21", 1)),
            base_url="http://test",
        ) as rotated:
            existing = await rotated.post(
                "/api/v1/auth/login",
                json={"email": email.upper(), "password": "wrong"},
            )
            unknown_email = f"{uuid.uuid4().hex}@example.com"
            await rotated.post(
                "/api/v1/auth/login",
                json={"email": unknown_email, "password": "wrong"},
            )
            unknown = await rotated.post(
                "/api/v1/auth/login",
                json={"email": unknown_email, "password": "wrong"},
            )

        assert existing.status_code == unknown.status_code == 429
        assert existing.json() == unknown.json()
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_creator_enrollment_is_throttled_per_user(client, monkeypatch):
    _set_limit(monkeypatch, "CREATOR_ENROLLMENT_LIMIT", 1)
    headers = await register_and_login(client, enroll=False)
    try:
        assert (
            await client.post("/api/v1/auth/creator/enroll", headers=headers)
        ).status_code == 200
        limited = await client.post("/api/v1/auth/creator/enroll", headers=headers)
        assert limited.status_code == 429
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_backtest_creation_is_throttled_per_user(client, monkeypatch):
    _set_limit(monkeypatch, "BACKTEST_BURST_LIMIT", 1)
    headers = await register_and_login(client)
    strategy, version = await create_strategy_version(
        client, headers, f"abuse-{uuid.uuid4().hex}"
    )
    path = backtests_path(strategy, version)
    payload = {}

    try:
        assert (await client.post(path, headers=headers, json=payload)).status_code == 201
        limited = await client.post(path, headers=headers, json=payload)
        assert limited.status_code == 429
        assert limited.json()["detail"]["error_code"] == "rate_limit_exceeded"
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_paper_execution_is_throttled_per_user(client, monkeypatch):
    from tests.test_paper_execution import create_paper_execution_intent, execute_path

    _, investor_headers, _, _, _, intent = await create_paper_execution_intent(
        client, f"abuse-execution-{uuid.uuid4().hex}"
    )
    await abuse_controller.clear()
    _set_limit(monkeypatch, "EXECUTION_BURST_LIMIT", 1)

    try:
        assert (
            await client.post(execute_path(intent["id"]), headers=investor_headers)
        ).status_code == 200
        limited = await client.post(execute_path(intent["id"]), headers=investor_headers)
        assert limited.status_code == 429
        assert limited.json()["detail"]["error_code"] == "rate_limit_exceeded"
    finally:
        get_settings.cache_clear()
