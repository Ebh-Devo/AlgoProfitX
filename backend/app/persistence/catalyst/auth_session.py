from __future__ import annotations

import hmac
import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.persistence.auth_session import RefreshSessionRecord, SessionTokenRejected
from app.persistence.catalyst.client import (
    CatalystPersistenceClient,
    CatalystPersistenceError,
)


SESSIONS_TABLE = "AlgoProfitXAuthSessions"
CLAIMS_TABLE = "AlgoProfitXRefreshClaims"
SLOTS_TABLE = "AlgoProfitXAuthSessionSlots"
_SAFE_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_SAFE_ROWID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SESSION_COLUMNS = (
    "ROWID, session_uuid, user_uuid, slot_key, refresh_token_hash, created_at, "
    "expires_at, rotated_at, revoked_at, last_used_at"
)
_SLOT_COLUMNS = "ROWID, slot_key, slot_index, user_uuid, session_uuid, assigned_at"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Auth session timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_timestamp(value: Any, label: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst session row has invalid {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalystPersistenceError(
            f"Catalyst session row has invalid {label}"
        ) from exc
    if parsed.tzinfo is None:
        raise CatalystPersistenceError(f"Catalyst session row has invalid {label}")
    return parsed.astimezone(timezone.utc)


def _literal(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid Catalyst {label}")
    return f"'{value}'"


def _hash(value: str, label: str) -> str:
    if not _SAFE_HEX.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def _slot_key(user_id: uuid.UUID, slot_index: int) -> str:
    return hashlib.sha256(f"{user_id}:{slot_index}".encode("ascii")).hexdigest()


def _row_id(row: dict[str, Any]) -> str:
    value = str(row.get("ROWID", ""))
    if not _SAFE_ROWID.fullmatch(value):
        raise CatalystPersistenceError("Catalyst returned an invalid session row")
    return value


class CatalystAuthSessionRepository:
    """Catalyst-backed refresh sessions with one-time rotation claims.

    ``claim_hash`` is native-unique. The winning request inserts the supplied
    token hash before rotating the session. A concurrent or later reuse cannot
    insert the same claim and revokes the session. If the subsequent session
    update fails, the token remains claimed and is therefore consumed.
    """

    def __init__(self, client: CatalystPersistenceClient) -> None:
        self._client = client

    @staticmethod
    def _session_from_row(row: dict[str, Any]) -> RefreshSessionRecord:
        try:
            session_id = uuid.UUID(str(row["session_uuid"]))
            user_id = uuid.UUID(str(row["user_uuid"]))
            token_hash = _hash(str(row["refresh_token_hash"]), "refresh token hash")
            _hash(str(row["slot_key"]), "session slot key")
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError(
                "Catalyst returned an invalid session row"
            ) from exc
        created_at = _parse_timestamp(row.get("created_at"), "creation time")
        expires_at = _parse_timestamp(row.get("expires_at"), "expiry time")
        assert created_at is not None and expires_at is not None
        return RefreshSessionRecord(
            id=session_id,
            user_id=user_id,
            refresh_token_hash=token_hash,
            created_at=created_at,
            expires_at=expires_at,
            rotated_at=_parse_timestamp(row.get("rotated_at"), "rotation time", optional=True),
            revoked_at=_parse_timestamp(row.get("revoked_at"), "revocation time", optional=True),
            last_used_at=_parse_timestamp(
                row.get("last_used_at"), "last-used time", optional=True
            ),
        )

    async def _session_row(self, session_id: uuid.UUID) -> dict[str, Any] | None:
        identifier = str(session_id)
        literal = _literal(identifier, _SAFE_UUID, "session ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_SESSION_COLUMNS} FROM {SESSIONS_TABLE} "
            f"WHERE session_uuid = {literal} LIMIT 1",
            SESSIONS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate session rows")
        _row_id(rows[0])
        return rows[0]

    async def _slot_rows(self, user_id: uuid.UUID) -> list[dict[str, Any]]:
        identifier = str(user_id)
        literal = _literal(identifier, _SAFE_UUID, "user ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_SLOT_COLUMNS} FROM {SLOTS_TABLE} "
            f"WHERE user_uuid = {literal}",
            SLOTS_TABLE,
        )
        seen: set[int] = set()
        for row in rows:
            _row_id(row)
            _hash(str(row.get("slot_key", "")), "session slot key")
            try:
                slot_index = int(str(row["slot_index"]))
                uuid.UUID(str(row["session_uuid"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise CatalystPersistenceError(
                    "Catalyst returned an invalid session slot"
                ) from exc
            if slot_index < 0 or slot_index in seen:
                raise CatalystPersistenceError(
                    "Catalyst returned an invalid session slot"
                )
            seen.add(slot_index)
            _parse_timestamp(row.get("assigned_at"), "slot assignment time")
        return rows

    async def _slot_row(self, slot_key: str) -> dict[str, Any] | None:
        literal = _literal(slot_key, _SAFE_HEX, "session slot key")
        rows = await self._client.async_query_rows(
            f"SELECT {_SLOT_COLUMNS} FROM {SLOTS_TABLE} "
            f"WHERE slot_key = {literal} LIMIT 1",
            SLOTS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate session slots")
        if str(rows[0].get("slot_key", "")) != slot_key:
            raise CatalystPersistenceError("Catalyst returned an invalid session slot")
        _row_id(rows[0])
        return rows[0]

    async def _owns_slot(self, row: dict[str, Any]) -> bool:
        slot = await self._slot_row(str(row.get("slot_key", "")))
        return slot is not None and str(slot.get("session_uuid")) == str(
            row.get("session_uuid")
        )

    async def _claim_exists(self, token_hash: str) -> bool:
        literal = _literal(token_hash, _SAFE_HEX, "refresh claim")
        rows = await self._client.async_query_rows(
            f"SELECT ROWID FROM {CLAIMS_TABLE} "
            f"WHERE claim_hash = {literal} LIMIT 1",
            CLAIMS_TABLE,
        )
        return len(rows) == 1

    async def _revoke_row(self, row: dict[str, Any], now: datetime) -> RefreshSessionRecord:
        if row.get("revoked_at") is None:
            revoked_at = _timestamp(now)
            await self._client.async_update_row(
                SESSIONS_TABLE,
                {"ROWID": _row_id(row), "revoked_at": revoked_at},
            )
            row = {**row, "revoked_at": revoked_at}
        return self._session_from_row(row)

    async def create_session(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        max_sessions: int,
    ) -> RefreshSessionRecord:
        token_hash = _hash(refresh_token_hash, "refresh token hash")
        if not 1 <= max_sessions <= 100:
            raise ValueError("Invalid maximum session count")
        now = datetime.now(timezone.utc)
        expiry = _utc(expires_at)
        if expiry <= now:
            raise ValueError("Auth session expiry must be in the future")
        for _attempt in range(max_sessions + 3):
            slots = await self._slot_rows(user_id)
            if len(slots) > max_sessions:
                raise CatalystPersistenceError("Catalyst session slot limit is invalid")
            occupied = {int(str(slot["slot_index"])) for slot in slots}
            available = next(
                (index for index in range(max_sessions) if index not in occupied),
                None,
            )
            if available is None:
                oldest = min(
                    slots,
                    key=lambda slot: (
                        _parse_timestamp(slot.get("assigned_at"), "slot assignment time"),
                        int(str(slot["slot_index"])),
                    ),
                )
                available = int(str(oldest["slot_index"]))
                displaced = uuid.UUID(str(oldest["session_uuid"]))
                await self._client.async_delete_row(SLOTS_TABLE, _row_id(oldest))
                await self._delete_session_data(displaced)

            slot_key = _slot_key(user_id, available)
            slot = {
                "slot_key": slot_key,
                "slot_index": str(available),
                "user_uuid": str(user_id),
                "session_uuid": str(session_id),
                "assigned_at": _timestamp(now),
            }
            try:
                inserted_slot = await self._client.async_insert_row(SLOTS_TABLE, slot)
            except CatalystPersistenceError:
                if await self._slot_row(slot_key) is not None:
                    continue
                raise

            row = {
                "session_uuid": str(session_id),
                "user_uuid": str(user_id),
                "slot_key": slot_key,
                "refresh_token_hash": token_hash,
                "created_at": _timestamp(now),
                "expires_at": _timestamp(expiry),
            }
            try:
                inserted = await self._client.async_insert_row(SESSIONS_TABLE, row)
                inserted_row = {**row, **inserted}
                _row_id(inserted_row)
                if not await self._owns_slot(inserted_row):
                    await self._delete_session_data(session_id)
                    continue
            except Exception:
                try:
                    await self._client.async_delete_row(
                        SLOTS_TABLE, _row_id({**slot, **inserted_slot})
                    )
                except (CatalystPersistenceError, ValueError):
                    pass
                raise
            return self._session_from_row(inserted_row)
        raise CatalystPersistenceError("Catalyst session slot contention")

    async def rotate_session(
        self,
        *,
        session_id: uuid.UUID,
        supplied_token_hash: str,
        replacement_token_hash: str,
        now: datetime | None = None,
    ) -> RefreshSessionRecord:
        supplied = _hash(supplied_token_hash, "refresh token hash")
        replacement = _hash(replacement_token_hash, "replacement token hash")
        if hmac.compare_digest(supplied, replacement):
            raise ValueError("Replacement refresh token must be new")
        moment = _utc(now or datetime.now(timezone.utc))
        row = await self._session_row(session_id)
        if row is None:
            raise SessionTokenRejected()
        current = self._session_from_row(row)
        if not await self._owns_slot(row):
            await self._revoke_row(row, moment)
            raise SessionTokenRejected()
        if not hmac.compare_digest(current.refresh_token_hash, supplied):
            await self._revoke_row(row, moment)
            raise SessionTokenRejected(suspicious_reuse=True)
        if current.revoked_at is not None or current.expires_at <= moment:
            raise SessionTokenRejected()

        claim = {
            "claim_hash": supplied,
            "session_uuid": str(session_id),
            "claimed_at": _timestamp(moment),
        }
        try:
            await self._client.async_insert_row(CLAIMS_TABLE, claim)
        except CatalystPersistenceError:
            if await self._claim_exists(supplied):
                latest = await self._session_row(session_id)
                if latest is not None:
                    await self._revoke_row(latest, moment)
                raise SessionTokenRejected(suspicious_reuse=True) from None
            raise

        latest = await self._session_row(session_id)
        if latest is None:
            raise SessionTokenRejected()
        checked = self._session_from_row(latest)
        if (
            checked.revoked_at is not None
            or checked.expires_at <= moment
            or not hmac.compare_digest(checked.refresh_token_hash, supplied)
        ):
            if checked.revoked_at is None:
                await self._revoke_row(latest, moment)
            raise SessionTokenRejected(
                suspicious_reuse=not hmac.compare_digest(
                    checked.refresh_token_hash, supplied
                )
            )

        timestamp = _timestamp(moment)
        await self._client.async_update_row(
            SESSIONS_TABLE,
            {
                "ROWID": _row_id(latest),
                "refresh_token_hash": replacement,
                "rotated_at": timestamp,
                "last_used_at": timestamp,
            },
        )
        return self._session_from_row(
            {
                **latest,
                "refresh_token_hash": replacement,
                "rotated_at": timestamp,
                "last_used_at": timestamp,
            }
        )

    async def revoke_session(
        self,
        *,
        session_id: uuid.UUID,
        supplied_token_hash: str,
        now: datetime | None = None,
    ) -> RefreshSessionRecord:
        supplied = _hash(supplied_token_hash, "refresh token hash")
        row = await self._session_row(session_id)
        if row is None:
            raise SessionTokenRejected()
        current = self._session_from_row(row)
        if not await self._owns_slot(row):
            raise SessionTokenRejected()
        if not hmac.compare_digest(current.refresh_token_hash, supplied):
            raise SessionTokenRejected()
        return await self._revoke_row(row, _utc(now or datetime.now(timezone.utc)))

    async def delete_session(self, session_id: uuid.UUID) -> bool:
        return await self._delete_session_data(session_id, remove_slot=True)

    async def _delete_session_data(
        self,
        session_id: uuid.UUID,
        *,
        remove_slot: bool = False,
    ) -> bool:
        identifier = str(session_id)
        literal = _literal(identifier, _SAFE_UUID, "session ID")
        claim_rows = await self._client.async_query_rows(
            f"SELECT ROWID FROM {CLAIMS_TABLE} "
            f"WHERE session_uuid = {literal}",
            CLAIMS_TABLE,
        )
        for claim in claim_rows:
            await self._client.async_delete_row(CLAIMS_TABLE, _row_id(claim))
        row = await self._session_row(session_id)
        if row is None:
            return False
        if remove_slot:
            slot = await self._slot_row(str(row.get("slot_key", "")))
            if slot is not None and str(slot.get("session_uuid")) == identifier:
                await self._client.async_delete_row(SLOTS_TABLE, _row_id(slot))
        await self._client.async_delete_row(SESSIONS_TABLE, _row_id(row))
        return True
