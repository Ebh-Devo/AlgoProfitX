from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.persistence.catalyst.client import (
    CatalystPersistenceClient,
    CatalystPersistenceError,
)
from app.persistence.identity import (
    DuplicateIdentityError,
    IdentityConfigurationError,
    IdentityRole,
    IdentityUser,
)


USERS_TABLE = "AlgoProfitXUsers"
ROLES_TABLE = "AlgoProfitXRoles"
DEFAULT_ROLE = "INVESTOR"
CREATOR_ROLE = "CREATOR"
_ALLOWED_ROLES = frozenset({DEFAULT_ROLE, CREATOR_ROLE})
_SAFE_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_USER_COLUMNS = (
    "ROWID, user_uuid, email, password_hash, is_active, is_verified, "
    "role_names, full_name, phone, created_at, updated_at"
)


def _email_lookup(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def _safe_literal(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid Catalyst {label}")
    return f"'{value}'"


def _parse_timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst user row has invalid {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalystPersistenceError(
            f"Catalyst user row has invalid {label}"
        ) from exc
    if parsed.tzinfo is None:
        raise CatalystPersistenceError(f"Catalyst user row has invalid {label}")
    return parsed


def _parse_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise CatalystPersistenceError(f"Catalyst user row has invalid {label}")


def _parse_roles(value: Any) -> tuple[IdentityRole, ...]:
    if not isinstance(value, str):
        raise CatalystPersistenceError("Catalyst user row has invalid roles")
    try:
        names = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CatalystPersistenceError("Catalyst user row has invalid roles") from exc
    if (
        not isinstance(names, list)
        or not names
        or any(not isinstance(name, str) or name not in _ALLOWED_ROLES for name in names)
        or len(names) != len(set(names))
    ):
        raise CatalystPersistenceError("Catalyst user row has invalid roles")
    return tuple(IdentityRole(name=name) for name in sorted(names))


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst user row has invalid {label}")
    return value


class CatalystIdentityRepository:
    """Identity records stored in Catalyst without exposing Catalyst ROWIDs.

    Email lookups use a SHA-256 key, and all ZCQL literals are fixed-format
    hashes or UUIDs. User-provided text is sent only through SDK row payloads.
    """

    def __init__(self, client: CatalystPersistenceClient) -> None:
        self._client = client

    @staticmethod
    def _user_from_row(row: dict[str, Any]) -> IdentityUser:
        try:
            user_id = uuid.UUID(str(row["user_uuid"]))
            email = str(row["email"])
            password_hash = str(row["password_hash"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError("Catalyst returned an invalid user row") from exc
        if not email or not password_hash:
            raise CatalystPersistenceError("Catalyst returned an invalid user row")
        return IdentityUser(
            id=user_id,
            email=email,
            password_hash=password_hash,
            is_active=_parse_bool(row.get("is_active"), "active state"),
            is_verified=_parse_bool(row.get("is_verified"), "verification state"),
            roles=_parse_roles(row.get("role_names")),
            full_name=_optional_text(row.get("full_name"), "full name"),
            phone=_optional_text(row.get("phone"), "phone"),
            created_at=_parse_timestamp(row.get("created_at"), "creation time"),
            updated_at=_parse_timestamp(row.get("updated_at"), "update time"),
        )

    async def _one_or_none(self, query: str) -> IdentityUser | None:
        rows = await self._client.async_query_rows(query, USERS_TABLE)
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate user rows")
        return self._user_from_row(rows[0])

    async def _role_exists(self, role_name: str) -> bool:
        if role_name not in _ALLOWED_ROLES:
            raise ValueError("Invalid identity role")
        rows = await self._client.async_query_rows(
            f"SELECT ROWID FROM {ROLES_TABLE} "
            f"WHERE role_name = '{role_name}' LIMIT 1",
            ROLES_TABLE,
        )
        return len(rows) == 1

    async def get_user_by_email(self, email: str) -> IdentityUser | None:
        lookup = _email_lookup(email)
        literal = _safe_literal(lookup, _SAFE_HEX, "email lookup")
        return await self._one_or_none(
            f"SELECT {_USER_COLUMNS} FROM {USERS_TABLE} "
            f"WHERE email_lookup = {literal} LIMIT 1"
        )

    async def get_user_by_id(self, user_id: uuid.UUID) -> IdentityUser | None:
        identifier = str(user_id)
        literal = _safe_literal(identifier, _SAFE_UUID, "user ID")
        return await self._one_or_none(
            f"SELECT {_USER_COLUMNS} FROM {USERS_TABLE} "
            f"WHERE user_uuid = {literal} LIMIT 1"
        )

    async def register_user(
        self,
        *,
        email: str,
        password_hash: str,
        full_name: str | None,
    ) -> IdentityUser:
        normalized_email = email.strip().lower()
        if not normalized_email or len(normalized_email) > 320:
            raise ValueError("Invalid identity email")
        if not password_hash or len(password_hash) > 255:
            raise ValueError("Invalid password hash")
        if full_name is not None and len(full_name) > 150:
            raise ValueError("Invalid full name")
        if not await self._role_exists(DEFAULT_ROLE):
            raise IdentityConfigurationError("Default user role is not configured")
        if await self.get_user_by_email(normalized_email) is not None:
            raise DuplicateIdentityError("Email is already registered")

        now = datetime.now(timezone.utc)
        row = {
            "user_uuid": str(uuid.uuid4()),
            "email_lookup": _email_lookup(normalized_email),
            "email": normalized_email,
            "password_hash": password_hash,
            "is_active": True,
            "is_verified": False,
            "role_names": json.dumps([DEFAULT_ROLE], separators=(",", ":")),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        if full_name:
            row["full_name"] = full_name
        try:
            inserted = await self._client.async_insert_row(USERS_TABLE, row)
        except CatalystPersistenceError:
            if await self.get_user_by_email(normalized_email) is not None:
                raise DuplicateIdentityError("Email is already registered") from None
            raise
        return self._user_from_row({**row, **inserted})

    async def enroll_creator(self, user_id: uuid.UUID) -> IdentityUser:
        if not await self._role_exists(CREATOR_ROLE):
            raise IdentityConfigurationError("Creator role is not configured")
        identifier = str(user_id)
        literal = _safe_literal(identifier, _SAFE_UUID, "user ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_USER_COLUMNS} FROM {USERS_TABLE} "
            f"WHERE user_uuid = {literal} LIMIT 1",
            USERS_TABLE,
        )
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst user was not found")
        current = self._user_from_row(rows[0])
        if any(role.name == CREATOR_ROLE for role in current.roles):
            return current
        row_id = str(rows[0].get("ROWID", ""))
        if not row_id:
            raise CatalystPersistenceError("Catalyst returned an invalid user row")
        role_names = sorted({role.name for role in current.roles} | {CREATOR_ROLE})
        updated_at = datetime.now(timezone.utc).isoformat()
        await self._client.async_update_row(
            USERS_TABLE,
            {
                "ROWID": row_id,
                "role_names": json.dumps(role_names, separators=(",", ":")),
                "updated_at": updated_at,
            },
        )
        updated_row = {
            **rows[0],
            "role_names": json.dumps(role_names, separators=(",", ":")),
            "updated_at": updated_at,
        }
        return self._user_from_row(updated_row)

    async def delete_user(self, user_id: uuid.UUID) -> bool:
        identifier = str(user_id)
        literal = _safe_literal(identifier, _SAFE_UUID, "user ID")
        rows = await self._client.async_query_rows(
            f"SELECT ROWID FROM {USERS_TABLE} "
            f"WHERE user_uuid = {literal} LIMIT 1",
            USERS_TABLE,
        )
        if not rows:
            return False
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate user rows")
        row_id = str(rows[0].get("ROWID", ""))
        if not row_id:
            raise CatalystPersistenceError("Catalyst returned an invalid user row")
        await self._client.async_delete_row(USERS_TABLE, row_id)
        return True
