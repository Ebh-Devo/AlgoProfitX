"""Issue #47: constant-time login for unknown/inactive accounts and no exception text on registration.

Catalyst-provider paths and the shared verifier. The SQL provider's equivalents are in
``test_auth_hardening_sql.py``. Nothing touches a live Catalyst environment.
"""

import dataclasses
import logging
import uuid

import pytest
from argon2 import extract_parameters
from httpx import ASGITransport, AsyncClient

from app.api.routes import auth as auth_routes
from app.core import security
from app.main import app
from app.persistence.catalyst.client import CatalystPersistenceError
from tests.test_catalyst_auth_routes import catalyst_auth  # noqa: F401  (pytest fixture)

PASSWORD = "TestPassword123"
GENERIC_LOGIN_BODY = {"detail": "Invalid email or password"}
SENTINEL = "SENTINEL-internal-detail-7f3a91"


def new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def verifier_calls(monkeypatch):
    """Record every full password verification and the hash it ran against."""
    calls: list[str] = []
    real = security.verify_password

    def spy(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return real(password, password_hash)

    monkeypatch.setattr(security, "verify_password", spy)
    return calls


async def register(client: AsyncClient, email: str):
    response = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201
    return response


# ------------------------------------------------------------------------- login timing parity


@pytest.mark.asyncio
async def test_every_login_outcome_runs_exactly_one_full_verification(catalyst_auth, verifier_calls):
    identity, sessions = catalyst_auth
    active_email = f"active-{uuid.uuid4().hex}@example.com"
    inactive_email = f"inactive-{uuid.uuid4().hex}@example.com"
    async with new_client() as client:
        await register(client, active_email)
        await register(client, inactive_email)
        inactive = next(user for user in identity.users.values() if user.email == inactive_email)
        identity.users[inactive.id] = dataclasses.replace(inactive, is_active=False)
        active = next(user for user in identity.users.values() if user.email == active_email)
        verifier_calls.clear()

        outcomes = {}
        for label, email, password in (
            ("wrong_password_active", active_email, "Wrong-Password-1"),
            ("correct_password_inactive", inactive_email, PASSWORD),
            ("unknown_account", f"nobody-{uuid.uuid4().hex}@example.com", PASSWORD),
        ):
            before = len(verifier_calls)
            response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
            outcomes[label] = (response, verifier_calls[before:])

    for label, (response, ran) in outcomes.items():
        assert len(ran) == 1, f"{label}: expected exactly one verification, got {len(ran)}"
        assert response.status_code == 401, label
        assert response.json() == GENERIC_LOGIN_BODY, label
        assert response.headers["www-authenticate"] == "Bearer", label
        assert "set-cookie" not in response.headers, label

    # Active and inactive accounts are verified against their own real hash; an unknown account
    # against the decoy, never against anyone's real hash.
    assert outcomes["wrong_password_active"][1] == [active.password_hash]
    assert outcomes["correct_password_inactive"][1] == [inactive.password_hash]
    decoy = security._decoy_password_hash()
    assert outcomes["unknown_account"][1] == [decoy]
    assert decoy not in {user.password_hash for user in identity.users.values()}

    # A failed login creates no session, slot or refresh claim.
    assert sessions.sessions == {} and sessions.claims == set()


@pytest.mark.asyncio
async def test_a_successful_login_also_runs_one_verification(catalyst_auth, verifier_calls):
    email = f"ok-{uuid.uuid4().hex}@example.com"
    async with new_client() as client:
        await register(client, email)
        verifier_calls.clear()
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200 and len(verifier_calls) == 1


@pytest.mark.asyncio
async def test_an_inactive_account_never_authenticates_even_with_the_correct_password(catalyst_auth):
    identity, sessions = catalyst_auth
    email = f"inactive-{uuid.uuid4().hex}@example.com"
    async with new_client() as client:
        await register(client, email)
        user = next(iter(identity.users.values()))
        identity.users[user.id] = dataclasses.replace(user, is_active=False)
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 401 and response.json() == GENERIC_LOGIN_BODY
    assert sessions.sessions == {}


def test_the_decoy_hash_uses_the_same_algorithm_and_cost_as_real_hashes():
    real = security.hash_password("a-real-password")
    decoy = security._decoy_password_hash()
    assert extract_parameters(decoy) == extract_parameters(real)
    assert decoy == security._decoy_password_hash()  # fixed for the process, not regenerated per request


def test_the_decoy_path_can_never_succeed(monkeypatch):
    assert security.verify_password_or_decoy("anything", None) is False
    # Even if the underlying verifier were to report a match, there is no account to authenticate.
    monkeypatch.setattr(security, "verify_password", lambda password, password_hash: True)
    assert security.verify_password_or_decoy("anything", None) is False
    assert security.verify_password_or_decoy("anything", "$argon2id$stub") is True


# ------------------------------------------------------------------- registration error leakage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        RuntimeError(SENTINEL),
        ValueError(SENTINEL),
        CatalystPersistenceError(SENTINEL),
        Exception(SENTINEL),
    ],
    ids=["RuntimeError", "ValueError", "CatalystPersistenceError", "Exception"],
)
async def test_unexpected_registration_failures_return_a_generic_500(catalyst_auth, caplog, error):
    identity, _ = catalyst_auth

    async def explode(**kwargs):
        raise error

    identity.register_user = explode
    secret_password = "Distinct-Registration-Secret-42"
    caplog.set_level(logging.ERROR, logger="app")
    async with new_client() as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": f"x-{uuid.uuid4().hex}@example.com", "password": secret_password},
        )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] and response.headers["x-request-id"] == body["request_id"]
    assert SENTINEL not in response.text and secret_password not in response.text

    # The detail is logged server-side, with the request id and without the password.
    records = [record for record in caplog.records if record.getMessage() == "registration_failed"]
    assert len(records) == 1
    record = records[0]
    assert SENTINEL in str(record.exc_info[1])
    assert record.fields["request_id"] == body["request_id"]
    assert secret_password not in caplog.text


@pytest.mark.asyncio
async def test_a_taken_email_still_returns_the_fixed_409(catalyst_auth):
    email = f"dup-{uuid.uuid4().hex}@example.com"
    async with new_client() as client:
        await register(client, email)
        again = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert again.status_code == 409
    assert again.json() == {"detail": "Email is already registered"}
