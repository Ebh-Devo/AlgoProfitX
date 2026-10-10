from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RefreshSessionRecord:
    id: uuid.UUID
    user_id: uuid.UUID
    refresh_token_hash: str
    created_at: datetime
    expires_at: datetime
    rotated_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None


class SessionTokenRejected(ValueError):
    def __init__(self, *, suspicious_reuse: bool = False) -> None:
        super().__init__("Invalid refresh session")
        self.suspicious_reuse = suspicious_reuse


class AuthSessionRepository(Protocol):
    async def create_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        max_sessions: int,
    ) -> RefreshSessionRecord: ...

    async def rotate_session(
        self,
        *,
        session_id: uuid.UUID,
        supplied_token_hash: str,
        replacement_token_hash: str,
        now: datetime | None = None,
    ) -> RefreshSessionRecord: ...

    async def revoke_session(
        self,
        *,
        session_id: uuid.UUID,
        supplied_token_hash: str,
        now: datetime | None = None,
    ) -> RefreshSessionRecord: ...

    async def delete_session(self, session_id: uuid.UUID) -> bool: ...
