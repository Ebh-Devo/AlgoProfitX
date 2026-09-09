import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.routes import auth as auth_routes
from app.core import dependencies
from app.core.config import AppEnvironment, get_settings
from app.main import app
from app.persistence.auth_session import RefreshSessionRecord, SessionTokenRejected
from app.persistence.identity import DuplicateIdentityError, IdentityRole, IdentityUser


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.users: dict[uuid.UUID, IdentityUser] = {}

    async def register_user(
        self, *, email: str, password_hash: str, full_name: str | None
    ) -> IdentityUser:
        normalized = email.strip().lower()
        if any(user.email == normalized for user in self.users.values()):
            raise DuplicateIdentityError("Email is already registered")
        now = datetime.now(timezone.utc)
        user = IdentityUser(
            id=uuid.uuid4(),
            email=normalized,
            password_hash=password_hash,
            is_active=True,
            is_verified=False,
            roles=(IdentityRole(name="INVESTOR"),),
            full_name=full_name,
            phone=None,
            created_at=now,
            updated_at=now,
        )
        self.users[user.id] = user
        return user

    async def get_user_by_email(self, email: str) -> IdentityUser | None:
        normalized = email.strip().lower()
        return next(
            (user for user in self.users.values() if user.email == normalized), None
        )

    async def get_user_by_id(self, user_id: uuid.UUID) -> IdentityUser | None:
        return self.users.get(user_id)

    async def enroll_creator(self, user_id: uuid.UUID) -> IdentityUser:
        current = self.users[user_id]
        updated = IdentityUser(
            id=current.id,
            email=current.email,
            password_hash=current.password_hash,
            is_active=current.is_active,
            is_verified=current.is_verified,
            roles=tuple(
                IdentityRole(name=name)
                for name in sorted({role.name for role in current.roles} | {"CREATOR"})
            ),
            full_name=current.full_name,
            phone=current.phone,
            created_at=current.created_at,
            updated_at=datetime.now(timezone.utc),
        )
        self.users[user_id] = updated
        return updated


class FakeAuthSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[uuid.UUID, RefreshSessionRecord] = {}
        self.claims: set[str] = set()

    async def create_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        max_sessions: int,
    ) -> RefreshSessionRecord:
        now = datetime.now(timezone.utc)
        record = RefreshSessionRecord(
            id=session_id,
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            created_at=now,
            expires_at=expires_at,
            rotated_at=None,
            revoked_at=None,
            last_used_at=None,
        )
        self.sessions[session_id] = record
        return record

    async def rotate_session(
        self,
        *,
        session_id: uuid.UUID,
        supplied_token_hash: str,
        replacement_token_hash: str,
        now: datetime | None = None,
    ) -> RefreshSessionRecord:
        record = self.sessions.get(session_id)
        if record is None:
            raise SessionTokenRejected()
        if supplied_token_hash in self.claims:
            self.sessions[session_id] = self._revoked(record)
            raise SessionTokenRejected(suspicious_reuse=True)
        if record.revoked_at is not None or not hmac.compare_digest(
            record.refresh_token_hash, supplied_token_hash
        ):
            self.sessions[session_id] = self._revoked(record)
            raise SessionTokenRejected(suspicious_reuse=True)
        self.claims.add(supplied_token_hash)
        moment = now or datetime.now(timezone.utc)
        rotated = RefreshSessionRecord(
            id=record.id,
            user_id=record.user_id,
            refresh_token_hash=replacement_token_hash,
            created_at=record.created_at,
            expires_at=record.expires_at,
            rotated_at=moment,
            revoked_at=None,
            last_used_at=moment,
        )
        self.sessions[session_id] = rotated
        return rotated

    async def revoke_session(
        self,
        *,
        session_id: uuid.UUID,
        supplied_token_hash: str,
        now: datetime | None = None,
    ) -> RefreshSessionRecord:
        record = self.sessions.get(session_id)
        if record is None or not hmac.compare_digest(
            record.refresh_token_hash, supplied_token_hash
        ):
            raise SessionTokenRejected()
        revoked = self._revoked(record, now)
        self.sessions[session_id] = revoked
        return revoked

    @staticmethod
    def _revoked(
        record: RefreshSessionRecord, now: datetime | None = None
    ) -> RefreshSessionRecord:
        return RefreshSessionRecord(
            id=record.id,
            user_id=record.user_id,
            refresh_token_hash=record.refresh_token_hash,
            created_at=record.created_at,
            expires_at=record.expires_at,
            rotated_at=record.rotated_at,
            revoked_at=now or datetime.now(timezone.utc),
            last_used_at=record.last_used_at,
        )


@pytest.fixture
def catalyst_auth(monkeypatch):
    identity = FakeIdentityRepository()
    sessions = FakeAuthSessionRepository()
    monkeypatch.setattr(auth_routes, "_uses_catalyst_auth", lambda: True)
    monkeypatch.setattr(
        auth_routes,
        "_catalyst_auth_repositories",
        lambda request: (identity, sessions),
    )
    monkeypatch.setattr(
        dependencies,
        "get_settings",
        lambda: type("DevelopmentSettings", (), {"app_env": AppEnvironment.DEVELOPMENT})(),
    )
    monkeypatch.setattr(dependencies, "CatalystPersistenceClient", lambda request: object())
    monkeypatch.setattr(
        dependencies, "CatalystIdentityRepository", lambda client: identity
    )
    return identity, sessions


@pytest.mark.asyncio
async def test_catalyst_public_auth_flow(catalyst_auth):
    identity, sessions = catalyst_auth
    email = f"catalyst-{uuid.uuid4().hex}@example.com"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        registered = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "TestPassword123", "full_name": "User"},
        )
        assert registered.status_code == 201
        assert registered.json()["roles"] == ["INVESTOR"]
        assert len(identity.users) == 1

        duplicate = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "TestPassword123"},
        )
        assert duplicate.status_code == 409

        rejected = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "WrongPassword123"},
        )
        assert rejected.status_code == 401

        logged_in = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "TestPassword123"},
        )
        assert logged_in.status_code == 200
        access_token = logged_in.json()["access_token"]
        settings = get_settings()
        original_refresh = client.cookies[settings.auth_refresh_cookie_name]
        csrf = client.cookies[settings.auth_csrf_cookie_name]
        assert hashlib.sha256(original_refresh.encode()).hexdigest() == next(
            iter(sessions.sessions.values())
        ).refresh_token_hash

        me = await client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        )
        assert me.status_code == 200
        assert me.json()["email"] == email

        enrolled = await client.post(
            "/api/v1/auth/creator/enroll",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert enrolled.status_code == 200
        assert enrolled.json()["roles"] == ["CREATOR", "INVESTOR"]

        refreshed = await client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf}
        )
        assert refreshed.status_code == 200
        rotated_refresh = client.cookies[settings.auth_refresh_cookie_name]
        rotated_csrf = client.cookies[settings.auth_csrf_cookie_name]
        assert rotated_refresh != original_refresh

        logged_out = await client.post(
            "/api/v1/auth/logout", headers={"X-CSRF-Token": rotated_csrf}
        )
        assert logged_out.status_code == 204
        assert next(iter(sessions.sessions.values())).revoked_at is not None


@pytest.mark.asyncio
async def test_catalyst_refresh_replay_is_rejected_and_revokes_session(catalyst_auth):
    _, sessions = catalyst_auth
    settings = get_settings()
    email = f"replay-{uuid.uuid4().hex}@example.com"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "TestPassword123"},
        )
        await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "TestPassword123"},
        )
        original_refresh = client.cookies[settings.auth_refresh_cookie_name]
        csrf = client.cookies[settings.auth_csrf_cookie_name]
        first = await client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf}
        )
        assert first.status_code == 200

        current_csrf = client.cookies[settings.auth_csrf_cookie_name]
        client.cookies.set(settings.auth_refresh_cookie_name, original_refresh)
        replay = await client.post(
            "/api/v1/auth/refresh", headers={"X-CSRF-Token": current_csrf}
        )
        assert replay.status_code == 401
        assert next(iter(sessions.sessions.values())).revoked_at is not None
