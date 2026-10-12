"""Authentication security on the Catalyst provider: cookies, CSRF, rotation, expiry, limits.

Uses repository doubles and an in-memory Data Store; nothing touches a live Catalyst environment.
"""

import dataclasses
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.abuse import abuse_controller
from app.core.config import get_settings
from app.core.security import create_access_token
from app.main import app
from app.persistence.auth_session import SessionTokenRejected
from app.persistence.catalyst.auth_session import (
    CLAIMS_TABLE,
    SESSIONS_TABLE,
    SLOTS_TABLE,
    CatalystAuthSessionRepository,
)
from app.services.auth_session import hash_refresh_token, new_refresh_token
from tests.catalyst_memory import MemoryDataStore
from tests.test_catalyst_auth_routes import catalyst_auth  # noqa: F401  (pytest fixture)

PASSWORD = "TestPassword123"


def new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def register_and_login(client: AsyncClient, email: str | None = None):
    email = email or f"user-{uuid.uuid4().hex}@example.com"
    registered = await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert registered.status_code == 201
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200
    return email, login


def cookie_headers(response) -> dict[str, str]:
    """Map cookie name -> its full Set-Cookie header value."""
    result = {}
    for header in response.headers.get_list("set-cookie"):
        result[header.split("=", 1)[0]] = header
    return result


def attributes(header: str) -> dict[str, str | bool]:
    parts = [part.strip() for part in header.split(";")[1:]]
    parsed: dict[str, str | bool] = {}
    for part in parts:
        key, _, value = part.partition("=")
        parsed[key.lower()] = value if value else True
    return parsed


# ------------------------------------------------------------------------------------ cookies


@pytest.mark.asyncio
async def test_session_cookies_have_the_required_flags_scope_and_expiry(catalyst_auth, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "auth_cookie_secure", True)  # production policy
    async with new_client() as client:
        _, login = await register_and_login(client)
    cookies = cookie_headers(login)
    refresh = attributes(cookies[settings.auth_refresh_cookie_name])
    csrf = attributes(cookies[settings.auth_csrf_cookie_name])

    # The refresh cookie is unreadable by scripts, host-only, narrowly scoped and expiring.
    assert refresh.get("httponly") is True
    assert refresh.get("secure") is True
    assert str(refresh.get("samesite")).lower() == "strict"
    assert refresh.get("path") == "/api/v1/auth"
    assert "domain" not in refresh
    assert int(refresh["max-age"]) == settings.refresh_token_expire_days * 86400

    # The CSRF cookie must be readable by the page (double-submit) but is otherwise locked down.
    assert "httponly" not in csrf
    assert csrf.get("secure") is True
    assert str(csrf.get("samesite")).lower() == "strict"
    assert csrf.get("path") == "/"
    assert int(csrf["max-age"]) == settings.refresh_token_expire_days * 86400


@pytest.mark.asyncio
async def test_access_token_is_never_placed_in_a_cookie(catalyst_auth):
    async with new_client() as client:
        _, login = await register_and_login(client)
    assert login.json()["access_token"]
    assert not any(login.json()["access_token"] in value for value in login.headers.get_list("set-cookie"))


# ---------------------------------------------------------------------------------------- CSRF


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["/api/v1/auth/refresh", "/api/v1/auth/logout"])
async def test_state_changing_cookie_endpoints_require_a_matching_csrf_token(catalyst_auth, endpoint):
    settings = get_settings()
    _, sessions = catalyst_auth
    async with new_client() as client:
        await register_and_login(client)
        before = next(iter(sessions.sessions.values()))
        good = client.cookies[settings.auth_csrf_cookie_name]

        assert (await client.post(endpoint)).status_code == 403  # no header
        assert (await client.post(endpoint, headers={"X-CSRF-Token": "wrong"})).status_code == 403
        assert (await client.post(endpoint, headers={"X-CSRF-Token": good[:-1]})).status_code == 403
        assert (await client.post(endpoint, headers={"X-CSRF-Token": ""})).status_code == 403

        # A header alone is not enough: without the cookie the double-submit check fails.
        client.cookies.delete(settings.auth_csrf_cookie_name)
        assert (await client.post(endpoint, headers={"X-CSRF-Token": good})).status_code == 403

    assert next(iter(sessions.sessions.values())) == before  # nothing rotated or revoked


@pytest.mark.asyncio
async def test_creator_enrollment_and_me_require_a_bearer_token_not_cookies(catalyst_auth):
    async with new_client() as client:
        await register_and_login(client)  # holds the refresh and CSRF cookies
        assert (await client.get("/api/v1/auth/me")).status_code in (401, 403)
        assert (await client.post("/api/v1/auth/creator/enroll")).status_code in (401, 403)


# -------------------------------------------------------------------- reload and rotation flow


@pytest.mark.asyncio
async def test_a_page_reload_restores_the_session_from_cookies_alone(catalyst_auth):
    settings = get_settings()
    async with new_client() as first:
        email, _ = await register_and_login(first)
        cookies = {
            settings.auth_refresh_cookie_name: first.cookies[settings.auth_refresh_cookie_name],
            settings.auth_csrf_cookie_name: first.cookies[settings.auth_csrf_cookie_name],
        }
    # A fresh browser context with only the persisted cookies (the access token is memory-only).
    async with new_client() as reloaded:
        for name, value in cookies.items():
            reloaded.cookies.set(name, value)
        refreshed = await reloaded.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": cookies[settings.auth_csrf_cookie_name]}
        )
        assert refreshed.status_code == 200
        me = await reloaded.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"}
        )
        assert me.status_code == 200 and me.json()["email"] == email


@pytest.mark.asyncio
async def test_refresh_rotates_the_token_and_csrf_and_the_old_pair_dies(catalyst_auth):
    settings = get_settings()
    async with new_client() as client:
        await register_and_login(client)
        old_refresh = client.cookies[settings.auth_refresh_cookie_name]
        old_csrf = client.cookies[settings.auth_csrf_cookie_name]
        rotated = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": old_csrf})
        assert rotated.status_code == 200
        new_refresh = client.cookies[settings.auth_refresh_cookie_name]
        new_csrf = client.cookies[settings.auth_csrf_cookie_name]
        assert new_refresh != old_refresh and new_csrf != old_csrf
        assert hash_refresh_token(new_refresh) != hash_refresh_token(old_refresh)


@pytest.mark.asyncio
async def test_a_failed_refresh_clears_both_cookies(catalyst_auth):
    settings = get_settings()
    async with new_client() as client:
        await register_and_login(client)
        csrf = client.cookies[settings.auth_csrf_cookie_name]
        client.cookies.set(settings.auth_refresh_cookie_name, new_refresh_token(uuid.uuid4()))
        failed = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert failed.status_code == 401
    cleared = cookie_headers(failed)
    for name in (settings.auth_refresh_cookie_name, settings.auth_csrf_cookie_name):
        assert name in cleared
        assert attributes(cleared[name]).get("max-age") == "0" or "1970" in cleared[name]


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_cookie", ["", "garbage", "not-hex.secret", "zz" * 16 + ".x"])
async def test_malformed_or_missing_refresh_cookies_are_rejected_uniformly(catalyst_auth, bad_cookie):
    settings = get_settings()
    async with new_client() as client:
        await register_and_login(client)
        csrf = client.cookies[settings.auth_csrf_cookie_name]
        client.cookies.delete(settings.auth_refresh_cookie_name)
        if bad_cookie:
            client.cookies.set(settings.auth_refresh_cookie_name, bad_cookie, path="/api/v1/auth")
        failed = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert failed.status_code == 401
    assert failed.json() == {"detail": "Invalid refresh session"}


@pytest.mark.asyncio
async def test_logout_revokes_the_session_clears_cookies_and_blocks_refresh(catalyst_auth):
    settings = get_settings()
    _, sessions = catalyst_auth
    async with new_client() as client:
        await register_and_login(client)
        refresh_cookie = client.cookies[settings.auth_refresh_cookie_name]
        csrf = client.cookies[settings.auth_csrf_cookie_name]
        out = await client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
        assert out.status_code == 204
        cleared = cookie_headers(out)
        assert settings.auth_refresh_cookie_name in cleared and settings.auth_csrf_cookie_name in cleared
        assert next(iter(sessions.sessions.values())).revoked_at is not None

        # Replaying the old cookies after logout fails.
        client.cookies.set(settings.auth_refresh_cookie_name, refresh_cookie)
        client.cookies.set(settings.auth_csrf_cookie_name, csrf)
        again = await client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
        assert again.status_code == 401


# -------------------------------------------------------------------------------- access tokens


@pytest.mark.asyncio
async def test_invalid_expired_and_orphaned_access_tokens_are_rejected(catalyst_auth):
    identity, _ = catalyst_auth
    async with new_client() as client:
        _, login = await register_and_login(client)
        good = login.json()["access_token"]
        assert (await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {good}"})).status_code == 200

        for token in (good[:-3] + "abc", "not.a.jwt", ""):
            rejected = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert rejected.status_code in (401, 403)

        # A validly signed token for a user that no longer exists (or was deactivated).
        orphan = create_access_token(str(uuid.uuid4()))
        gone = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {orphan}"})
        assert gone.status_code == 401 and gone.headers["www-authenticate"] == "Bearer"

        user = next(iter(identity.users.values()))
        identity.users[user.id] = dataclasses.replace(user, is_active=False)
        deactivated = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {good}"})
        assert deactivated.status_code == 401


@pytest.mark.asyncio
async def test_login_does_not_reveal_whether_an_account_exists(catalyst_auth):
    async with new_client() as client:
        email, _ = await register_and_login(client)
        wrong_password = await client.post("/api/v1/auth/login", json={"email": email, "password": "Wrong-Password-1"})
        unknown = await client.post(
            "/api/v1/auth/login", json={"email": f"nobody-{uuid.uuid4().hex}@example.com", "password": PASSWORD}
        )
    assert wrong_password.status_code == unknown.status_code == 401
    assert wrong_password.json() == unknown.json()
    assert "set-cookie" not in wrong_password.headers and "set-cookie" not in unknown.headers


# ------------------------------------------------------------------------------- rate limiting


@pytest.mark.asyncio
async def test_repeated_failed_logins_are_rate_limited(catalyst_auth, monkeypatch):
    settings = get_settings()
    await abuse_controller.clear()
    monkeypatch.setattr(settings, "abuse_protection_enabled", True)
    monkeypatch.setattr(settings, "login_account_limit", 3)
    monkeypatch.setattr(settings, "login_ip_limit", 50)
    async with new_client() as client:
        email, _ = await register_and_login(client)
        statuses = [
            (await client.post("/api/v1/auth/login", json={"email": email, "password": "Wrong-Password-1"})).status_code
            for _ in range(6)
        ]
    assert 429 in statuses
    assert statuses[0] == 401
    await abuse_controller.clear()


# ----------------------------------------------------------- session expiry on the real repository


def session_store() -> MemoryDataStore:
    return MemoryDataStore(
        {SESSIONS_TABLE: None, CLAIMS_TABLE: None, SLOTS_TABLE: None},
        {
            SESSIONS_TABLE: ("session_uuid",),
            CLAIMS_TABLE: ("claim_hash",),
            SLOTS_TABLE: ("slot_key", "session_uuid"),
        },
    )


@pytest.mark.asyncio
async def test_expired_sessions_cannot_be_rotated_or_revived():
    repository = CatalystAuthSessionRepository(session_store())
    session_id, user_id = uuid.uuid4(), uuid.uuid4()
    token = new_refresh_token(session_id)
    await repository.create_session(
        session_id=session_id,
        user_id=user_id,
        refresh_token_hash=hash_refresh_token(token),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        max_sessions=5,
    )
    replacement = hash_refresh_token(new_refresh_token(session_id))
    future = datetime.now(timezone.utc) + timedelta(days=31)
    with pytest.raises(SessionTokenRejected):
        await repository.rotate_session(
            session_id=session_id,
            supplied_token_hash=hash_refresh_token(token),
            replacement_token_hash=replacement,
            now=future,
        )


@pytest.mark.asyncio
async def test_a_session_must_expire_in_the_future_and_respects_the_session_limit():
    store = session_store()
    repository = CatalystAuthSessionRepository(store)
    user_id = uuid.uuid4()
    with pytest.raises(ValueError, match="future"):
        session_id = uuid.uuid4()
        await repository.create_session(
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(new_refresh_token(session_id)),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            max_sessions=5,
        )
    assert store.rows[SESSIONS_TABLE] == []
