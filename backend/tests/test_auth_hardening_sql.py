"""Issue #47 on the SQL provider (local PostgreSQL test tooling): login timing parity and registration leakage."""

import logging
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.api.routes import auth as auth_routes
from app.core import security
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.auth_session import AuthSession
from app.models.user import User

PASSWORD = "TestPassword123"
GENERIC_LOGIN_BODY = {"detail": "Invalid email or password"}
SENTINEL = "SENTINEL-internal-detail-91c0de"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def verifier_calls(monkeypatch):
    calls: list[str] = []
    real = security.verify_password

    def spy(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return real(password, password_hash)

    monkeypatch.setattr(security, "verify_password", spy)
    return calls


def unique_email(prefix: str = "sql") -> str:
    return f"{prefix}-{uuid.uuid4().hex}@example.com"


async def register(client, email):
    response = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return response


async def session_count() -> int:
    async with AsyncSessionLocal() as session:
        return await session.scalar(select(func.count()).select_from(AuthSession))


@pytest.mark.asyncio
async def test_every_sql_login_outcome_runs_exactly_one_full_verification(client, verifier_calls):
    active, inactive = unique_email("active"), unique_email("inactive")
    await register(client, active)
    await register(client, inactive)
    async with AsyncSessionLocal() as session:
        await session.execute(update(User).where(User.email == inactive).values(is_active=False))
        await session.commit()
        hashes = dict((await session.execute(select(User.email, User.password_hash))).all())
    verifier_calls.clear()

    outcomes = {}
    for label, email, password in (
        ("wrong_password_active", active, "Wrong-Password-1"),
        ("correct_password_inactive", inactive, PASSWORD),
        ("unknown_account", unique_email("nobody"), PASSWORD),
    ):
        before = len(verifier_calls)
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        outcomes[label] = (response, verifier_calls[before:])

    for label, (response, ran) in outcomes.items():
        assert len(ran) == 1, f"{label}: expected exactly one verification, got {len(ran)}"
        assert response.status_code == 401 and response.json() == GENERIC_LOGIN_BODY, label
        assert response.headers["www-authenticate"] == "Bearer", label
        assert "set-cookie" not in response.headers, label

    assert outcomes["wrong_password_active"][1] == [hashes[active]]
    assert outcomes["correct_password_inactive"][1] == [hashes[inactive]]
    assert outcomes["unknown_account"][1] == [security._decoy_password_hash()]
    assert security._decoy_password_hash() not in hashes.values()
    assert await session_count() == 0  # failures create no session or refresh claim


@pytest.mark.asyncio
async def test_a_successful_sql_login_runs_one_verification_and_creates_one_session(client, verifier_calls):
    email = unique_email()
    await register(client, email)
    verifier_calls.clear()
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200 and len(verifier_calls) == 1
    assert await session_count() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError(SENTINEL), ValueError(SENTINEL), Exception(SENTINEL)])
async def test_unexpected_sql_registration_failures_return_a_generic_500(client, monkeypatch, caplog, error):
    async def explode(session, data):
        raise error

    monkeypatch.setattr(auth_routes, "register_user", explode)
    secret_password = "Distinct-Registration-Secret-77"
    caplog.set_level(logging.ERROR, logger="app")
    response = await client.post(
        "/api/v1/auth/register", json={"email": unique_email(), "password": secret_password}
    )
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error" and body["request_id"]
    assert SENTINEL not in response.text and secret_password not in response.text
    records = [r for r in caplog.records if r.getMessage() == "registration_failed"]
    assert len(records) == 1 and SENTINEL in str(records[0].exc_info[1])
    assert records[0].fields["request_id"] == body["request_id"]
    assert secret_password not in caplog.text


@pytest.mark.asyncio
async def test_a_taken_email_still_returns_the_fixed_409_on_sql(client):
    email = unique_email()
    await register(client, email)
    again = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert again.status_code == 409 and again.json() == {"detail": "Email is already registered"}
    upper = await client.post("/api/v1/auth/register", json={"email": email.upper(), "password": PASSWORD})
    assert upper.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError(SENTINEL), ValueError(SENTINEL), Exception(SENTINEL)])
async def test_unexpected_sql_creator_enrollment_failures_return_a_generic_500(client, monkeypatch, caplog, error):
    email = unique_email()
    password = "Distinct-Enrollment-Secret-55"
    assert (await client.post("/api/v1/auth/register", json={"email": email, "password": password})).status_code == 201
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["access_token"]

    async def explode(session, user):
        raise error

    monkeypatch.setattr(auth_routes, "enroll_creator", explode)
    caplog.set_level(logging.ERROR, logger="app")
    response = await client.post("/api/v1/auth/creator/enroll", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error" and body["request_id"]
    assert response.headers["x-request-id"] == body["request_id"]
    assert SENTINEL not in response.text
    records = [r for r in caplog.records if r.getMessage() == "creator_enrollment_failed"]
    assert len(records) == 1 and SENTINEL in str(records[0].exc_info[1])
    assert records[0].fields["request_id"] == body["request_id"]
    assert password not in caplog.text and token not in caplog.text
