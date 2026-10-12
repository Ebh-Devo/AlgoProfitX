"""Issue #47: constant-time login for unknown/inactive accounts and no exception text on registration.

Catalyst-provider paths and the shared verifier. The SQL provider's equivalents are in
``test_auth_hardening_sql.py``. Nothing touches a live Catalyst environment.
"""

import dataclasses
import logging
import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path

import pytest
from argon2 import extract_parameters
from httpx import ASGITransport, AsyncClient

from app.api.routes import auth as auth_routes
from app.core import security
from app.main import app
from app.persistence.catalyst.client import CatalystPersistenceError
from tests.test_catalyst_auth_routes import catalyst_auth  # noqa: F401  (pytest fixture)

BACKEND = Path(__file__).resolve().parents[1]
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


@pytest.mark.asyncio
async def test_login_never_generates_a_hash_so_the_first_unknown_account_pays_no_extra_cost(
    catalyst_auth, monkeypatch, verifier_calls
):
    """The decoy exists before any request; no login outcome may call hash generation."""

    class VerifyOnlyHasher:
        """Delegates verification; any attempt to generate a hash fails the test."""

        def __init__(self, real):
            self._real = real

        def hash(self, *args, **kwargs):
            raise AssertionError("a password hash was generated while handling a login request")

        def verify(self, *args, **kwargs):
            return self._real.verify(*args, **kwargs)

    # Cold start: if an implementation caches the decoy lazily, drop the cache so this login would
    # have to generate it (and fail). The eager implementation has nothing to clear.
    getattr(security._decoy_password_hash, "cache_clear", lambda: None)()
    monkeypatch.setattr(security, "password_hasher", VerifyOnlyHasher(security.password_hasher))
    async with new_client() as client:
        first_unknown = await client.post(
            "/api/v1/auth/login", json={"email": f"nobody-{uuid.uuid4().hex}@example.com", "password": PASSWORD}
        )
    assert first_unknown.status_code == 401 and first_unknown.json() == GENERIC_LOGIN_BODY
    assert verifier_calls == [security._decoy_password_hash()]  # exactly one verification, of the decoy


IMPORT_PROBE = textwrap.dedent(
    """
    import argon2
    calls = []
    real = argon2.PasswordHasher.hash

    def counting(self, *args, **kwargs):
        calls.append(1)
        return real(self, *args, **kwargs)

    argon2.PasswordHasher.hash = counting
    import app.core.config as config
    config.Settings.model_config["env_file"] = None
    import app.core.security as security
    assert len(calls) == 1, f"decoy not created at import: {len(calls)}"
    assert security.verify_password_or_decoy("x", None) is False
    assert security.verify_password_or_decoy("y", None) is False
    assert len(calls) == 1, "a hash was generated while verifying"
    print("ok")
    """
)


def _probe_environment() -> dict:
    environment = {key: value for key, value in os.environ.items() if key not in {"DATABASE_URL", "PERSISTENCE_PROVIDER"}}
    environment.update(APP_ENV="development", PERSISTENCE_PROVIDER="catalyst", SECRET_KEY="a-long-unique-secret-for-this-probe")
    return environment


def test_the_decoy_is_created_at_import_and_never_during_verification():
    """In a fresh process: exactly one hash is generated while importing, none when verifying."""
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_PROBE], cwd=BACKEND, env=_probe_environment(), capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0 and result.stdout.strip() == "ok", result.stderr[-1500:]
    assert "argon2" not in result.stdout  # the decoy hash itself is never printed


def test_the_decoy_secret_is_random_per_process():
    """Two processes get different decoys, so nothing about it is constant or predictable."""
    program = (
        "import app.core.config as c; c.Settings.model_config['env_file'] = None; "
        "import app.core.security as s; print(s._decoy_password_hash())"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", program], cwd=BACKEND, env=_probe_environment(), capture_output=True, text=True, timeout=120
        ).stdout.strip()
        for _ in range(2)
    }
    assert len(outputs) == 2 and all(value.startswith("$argon2") for value in outputs)


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


# ------------------------------------------------------------ creator-enrollment error leakage


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
async def test_unexpected_creator_enrollment_failures_return_a_generic_500(catalyst_auth, caplog, error):
    identity, _ = catalyst_auth
    email = f"enroll-{uuid.uuid4().hex}@example.com"
    async with new_client() as client:
        await register(client, email)
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        assert login.status_code == 200
        token = login.json()["access_token"]

        async def explode(user_id):
            raise error

        identity.enroll_creator = explode
        caplog.set_level(logging.ERROR, logger="app")
        response = await client.post(
            "/api/v1/auth/creator/enroll", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error"
    assert body["request_id"] and response.headers["x-request-id"] == body["request_id"]
    assert SENTINEL not in response.text

    records = [record for record in caplog.records if record.getMessage() == "creator_enrollment_failed"]
    assert len(records) == 1
    record = records[0]
    assert SENTINEL in str(record.exc_info[1])
    assert record.fields["request_id"] == body["request_id"]
    assert PASSWORD not in caplog.text and token not in caplog.text


@pytest.mark.asyncio
async def test_an_intentional_http_error_from_enrollment_is_preserved(catalyst_auth):
    from fastapi import HTTPException

    identity, _ = catalyst_auth
    email = f"enroll-http-{uuid.uuid4().hex}@example.com"
    async with new_client() as client:
        await register(client, email)
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
        token = login.json()["access_token"]

        async def refuse(user_id):
            raise HTTPException(status_code=409, detail="Already a creator")

        identity.enroll_creator = refuse
        response = await client.post(
            "/api/v1/auth/creator/enroll", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 409
    assert response.json() == {"detail": "Already a creator"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message, leaked",
    [
        ("upstream rejected password=Hunter2-Distinct-Value", "Hunter2-Distinct-Value"),
        ('config {"api_key": "key-Distinct-9981"} invalid', "key-Distinct-9981"),
        ("call failed: Authorization: Bearer abc.def.Distinct-jwt", "Distinct-jwt"),
        ("connect postgresql://app:Distinct-dbpass@db.example.com/x failed", "Distinct-dbpass"),
        ("refresh_token=Distinct-refresh-777 expired", "Distinct-refresh-777"),
    ],
)
async def test_secrets_labelled_in_an_exception_message_are_redacted_from_the_log(
    catalyst_auth, capsys, message, leaked
):
    """Redaction is best effort: it covers labelled secrets (name=value, JSON, bearer, DB URL)."""
    from app.core.observability import JsonFormatter

    identity, _ = catalyst_auth
    email = f"enroll-redact-{uuid.uuid4().hex}@example.com"
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    logger = logging.getLogger("app")
    logger.addHandler(handler)
    try:
        async with new_client() as client:
            await register(client, email)
            token = (
                await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
            ).json()["access_token"]

            async def explode(user_id):
                raise RuntimeError(message)

            identity.enroll_creator = explode
            response = await client.post(
                "/api/v1/auth/creator/enroll", headers={"Authorization": f"Bearer {token}"}
            )
    finally:
        logger.removeHandler(handler)

    assert response.status_code == 500 and leaked not in response.text
    failure = [r for r in records if r.getMessage() == "creator_enrollment_failed"]
    assert len(failure) == 1
    rendered = JsonFormatter().format(failure[0])
    assert leaked not in rendered
    assert "[REDACTED]" in rendered
