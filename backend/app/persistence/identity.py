from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class IdentityRole:
    name: str


@dataclass(frozen=True, slots=True)
class IdentityUser:
    id: uuid.UUID
    email: str
    password_hash: str
    is_active: bool
    is_verified: bool
    roles: tuple[IdentityRole, ...]
    full_name: str | None
    phone: str | None
    created_at: datetime
    updated_at: datetime


class DuplicateIdentityError(ValueError):
    pass


class IdentityConfigurationError(RuntimeError):
    pass


class IdentityRepository(Protocol):
    async def get_user_by_email(self, email: str) -> IdentityUser | None: ...

    async def get_user_by_id(self, user_id: uuid.UUID) -> IdentityUser | None: ...

    async def register_user(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str | None,
    ) -> IdentityUser: ...

    async def enroll_creator(self, user_id: uuid.UUID) -> IdentityUser: ...
