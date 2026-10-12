import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.auth_session import AuthSession
from app.models.user import User


class RefreshSessionError(Exception):
    def __init__(self, suspicious_reuse: bool = False) -> None:
        super().__init__("Invalid refresh session")
        self.suspicious_reuse = suspicious_reuse


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token(session_id: uuid.UUID) -> str:
    return f"{session_id.hex}.{secrets.token_urlsafe(48)}"


def session_id_from_token(token: str) -> uuid.UUID:
    try:
        identifier, secret = token.split(".", 1)
        if not secret:
            raise ValueError
        return uuid.UUID(hex=identifier)
    except (ValueError, AttributeError) as exc:
        raise RefreshSessionError() from exc


async def create_refresh_session(
    session: AsyncSession, user_id: uuid.UUID
) -> tuple[AuthSession, str]:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(AuthSession)
        .where(AuthSession.user_id == user_id)
        .order_by(AuthSession.created_at.desc(), AuthSession.id.desc())
        .with_for_update()
    )
    existing = list(result.scalars())
    for stale in existing[settings.auth_max_sessions_per_user - 1 :]:
        await session.delete(stale)

    auth_session = AuthSession(
        user_id=user_id,
        refresh_token_hash="pending",
        expires_at=now + timedelta(days=settings.refresh_token_expire_days),
    )
    session.add(auth_session)
    await session.flush()
    refresh_token = new_refresh_token(auth_session.id)
    auth_session.refresh_token_hash = hash_refresh_token(refresh_token)
    return auth_session, refresh_token


async def rotate_refresh_session(
    session: AsyncSession, refresh_token: str
) -> tuple[User, str]:
    session_id = session_id_from_token(refresh_token)
    result = await session.execute(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    )
    auth_session = result.scalar_one_or_none()
    if auth_session is None:
        raise RefreshSessionError()

    now = datetime.now(timezone.utc)
    supplied_hash = hash_refresh_token(refresh_token)
    if not hmac.compare_digest(auth_session.refresh_token_hash, supplied_hash):
        auth_session.revoked_at = auth_session.revoked_at or now
        raise RefreshSessionError(suspicious_reuse=True)
    if auth_session.revoked_at is not None or auth_session.expires_at <= now:
        raise RefreshSessionError()

    user_result = await session.execute(select(User).where(User.id == auth_session.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        auth_session.revoked_at = now
        raise RefreshSessionError()

    rotated_token = new_refresh_token(auth_session.id)
    auth_session.refresh_token_hash = hash_refresh_token(rotated_token)
    auth_session.rotated_at = now
    auth_session.last_used_at = now
    return user, rotated_token


async def revoke_refresh_session(
    session: AsyncSession, refresh_token: str
) -> None:
    session_id = session_id_from_token(refresh_token)
    result = await session.execute(
        select(AuthSession).where(AuthSession.id == session_id).with_for_update()
    )
    auth_session = result.scalar_one_or_none()
    if auth_session is None or not hmac.compare_digest(
        auth_session.refresh_token_hash, hash_refresh_token(refresh_token)
    ):
        raise RefreshSessionError()
    auth_session.revoked_at = auth_session.revoked_at or datetime.now(timezone.utc)
