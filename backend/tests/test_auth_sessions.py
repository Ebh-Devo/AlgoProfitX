import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import ALGORITHM, decode_access_token
from app.db.session import AsyncSessionLocal
from app.models.auth_session import AuthSession
from app.main import app


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


def unique_email() -> str:
    return f"session-{uuid.uuid4().hex}@example.com"


async def register_and_login(client, email: str | None = None):
    email = email or unique_email()
    assert (
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "TestPassword123"},
        )
    ).status_code == 201
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "TestPassword123"},
    )
    assert response.status_code == 200
    return response


def csrf_headers(client) -> dict[str, str]:
    settings = get_settings()
    return {"X-CSRF-Token": client.cookies.get(settings.auth_csrf_cookie_name)}


@pytest.mark.asyncio
async def test_login_creates_hashed_session_and_secure_cookie_shape(client):
    response = await register_and_login(client)
    settings = get_settings()
    refresh = client.cookies.get(settings.auth_refresh_cookie_name)
    assert refresh
    assert "refresh" not in response.json()
    set_cookies = response.headers.get_list("set-cookie")
    refresh_header = next(item for item in set_cookies if settings.auth_refresh_cookie_name in item)
    assert "HttpOnly" in refresh_header
    assert "SameSite=strict" in refresh_header
    assert "Path=/api/v1/auth" in refresh_header

    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(AuthSession))).scalar_one()
        assert refresh not in stored.refresh_token_hash
        assert len(stored.refresh_token_hash) == 64


@pytest.mark.asyncio
async def test_refresh_rotates_and_old_token_reuse_revokes_session(client):
    await register_and_login(client)
    settings = get_settings()
    old_refresh = client.cookies.get(settings.auth_refresh_cookie_name)
    response = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert response.status_code == 200
    assert response.json()["access_token"]
    assert client.cookies.get(settings.auth_refresh_cookie_name) != old_refresh

    client.cookies.set(
        settings.auth_refresh_cookie_name,
        old_refresh,
        path=settings.auth_cookie_path,
    )
    reused = await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    assert reused.status_code == 401
    assert any(
        settings.auth_refresh_cookie_name in value and "Max-Age=0" in value
        for value in reused.headers.get_list("set-cookie")
    )
    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(AuthSession))).scalar_one()
        assert stored.revoked_at is not None


@pytest.mark.asyncio
async def test_expired_and_revoked_refresh_sessions_are_rejected(client):
    await register_and_login(client)
    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(AuthSession))).scalar_one()
        stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await session.commit()
    assert (
        await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    ).status_code == 401

    await register_and_login(client)
    async with AsyncSessionLocal() as session:
        stored = (
            await session.execute(
                select(AuthSession).order_by(AuthSession.created_at.desc())
            )
        ).scalars().first()
        stored.revoked_at = datetime.now(timezone.utc)
        await session.commit()
    assert (
        await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    ).status_code == 401


@pytest.mark.asyncio
async def test_refresh_and_logout_require_matching_csrf(client):
    await register_and_login(client)
    assert (await client.post("/api/v1/auth/refresh")).status_code == 403
    assert (
        await client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": "wrong"}
        )
    ).status_code == 403
    assert (
        await client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
    ).status_code == 200


@pytest.mark.asyncio
async def test_logout_revokes_session_and_clears_cookies(client):
    await register_and_login(client)
    response = await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    assert response.status_code == 204
    settings = get_settings()
    assert client.cookies.get(settings.auth_refresh_cookie_name) is None
    assert client.cookies.get(settings.auth_csrf_cookie_name) is None
    async with AsyncSessionLocal() as session:
        stored = (await session.execute(select(AuthSession))).scalar_one()
        assert stored.revoked_at is not None


@pytest.mark.asyncio
async def test_max_session_policy_bounds_persisted_sessions(client):
    email = unique_email()
    await register_and_login(client, email)
    settings = get_settings()
    for _ in range(settings.auth_max_sessions_per_user + 2):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "TestPassword123"},
        )
        assert response.status_code == 200
    async with AsyncSessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(AuthSession))
        assert count == settings.auth_max_sessions_per_user


def test_access_token_has_hardened_claims_and_key_identifier():
    from app.core.security import create_access_token

    token = create_access_token(str(uuid.uuid4()))
    payload = decode_access_token(token)
    assert {"sub", "type", "exp", "iat", "iss", "aud", "jti"} <= payload.keys()
    assert uuid.UUID(payload["jti"])
    assert jwt.get_unverified_header(token)["kid"] == get_settings().auth_jwt_key_id


@pytest.mark.parametrize(("claim", "value"), (("iss", "wrong"), ("aud", "wrong"), ("type", "refresh")))
def test_access_token_rejects_wrong_issuer_audience_or_type(claim: str, value: str):
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid.uuid4()), "type": "access", "iat": now,
        "exp": now + timedelta(minutes=5), "iss": settings.auth_jwt_issuer,
        "aud": settings.auth_jwt_audience, "jti": str(uuid.uuid4()),
    }
    payload[claim] = value
    token = jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=ALGORITHM,
        headers={"kid": settings.auth_jwt_key_id},
    )
    with pytest.raises(ValueError):
        decode_access_token(token)
