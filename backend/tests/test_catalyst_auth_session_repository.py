import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.persistence.auth_session import SessionTokenRejected
from app.persistence.catalyst.auth_session import (
    CLAIMS_TABLE,
    SESSIONS_TABLE,
    SLOTS_TABLE,
    CatalystAuthSessionRepository,
)
from app.persistence.catalyst.client import CatalystPersistenceError


SESSION_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
USER_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 9, 9, 8, 0, tzinfo=timezone.utc)
TOKEN_HASH = "a" * 64
NEW_TOKEN_HASH = "b" * 64
SLOT_KEY = hashlib.sha256(f"{USER_ID}:0".encode("ascii")).hexdigest()


def session_row(
    *,
    session_id: uuid.UUID = SESSION_ID,
    row_id: str = "session-row",
    token_hash: str = TOKEN_HASH,
    created_at: datetime = NOW,
) -> dict[str, object]:
    return {
        "ROWID": row_id,
        "session_uuid": str(session_id),
        "user_uuid": str(USER_ID),
        "slot_key": SLOT_KEY,
        "refresh_token_hash": token_hash,
        "created_at": created_at.isoformat(),
        "expires_at": (NOW + timedelta(days=30)).isoformat(),
        "rotated_at": None,
        "revoked_at": None,
        "last_used_at": None,
    }


def slot_row(
    *,
    session_id: uuid.UUID = SESSION_ID,
    row_id: str = "slot-row",
    slot_index: int = 0,
    assigned_at: datetime = NOW,
    slot_key: str = SLOT_KEY,
) -> dict[str, object]:
    return {
        "ROWID": row_id,
        "slot_key": slot_key,
        "slot_index": str(slot_index),
        "user_uuid": str(USER_ID),
        "session_uuid": str(session_id),
        "assigned_at": assigned_at.isoformat(),
    }


def client() -> SimpleNamespace:
    return SimpleNamespace(
        async_query_rows=AsyncMock(),
        async_insert_row=AsyncMock(),
        async_update_row=AsyncMock(),
        async_delete_row=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_create_session_claims_native_slot_and_keeps_hash_out_of_zcql():
    persistence = client()
    persistence.async_insert_row.side_effect = [
        {"ROWID": "new-slot"},
        {"ROWID": "new-session"},
    ]
    persistence.async_query_rows.side_effect = [[], [slot_row(row_id="new-slot")]]
    repository = CatalystAuthSessionRepository(persistence)

    created = await repository.create_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        refresh_token_hash=TOKEN_HASH,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        max_sessions=5,
    )

    assert created.user_id == USER_ID
    slot_table, slot_payload = persistence.async_insert_row.await_args_list[0].args
    session_table, session_payload = persistence.async_insert_row.await_args_list[1].args
    assert slot_table == SLOTS_TABLE
    assert session_table == SESSIONS_TABLE
    assert slot_payload["session_uuid"] == session_payload["session_uuid"]
    assert session_payload["refresh_token_hash"] == TOKEN_HASH
    query = persistence.async_query_rows.await_args_list[0].args[0]
    assert str(USER_ID) in query
    assert TOKEN_HASH not in query


@pytest.mark.asyncio
async def test_create_session_reclaims_oldest_native_slot_at_limit():
    persistence = client()
    newer_id = uuid.UUID("33333333-3333-4333-8333-333333333333")
    older_id = uuid.UUID("55555555-5555-4555-8555-555555555555")
    newer_slot = slot_row(
        session_id=newer_id,
        row_id="newer-slot",
        slot_index=1,
        assigned_at=NOW + timedelta(minutes=1),
        slot_key="d" * 64,
    )
    older_slot = slot_row(session_id=older_id, row_id="old-slot", slot_index=0)
    older_session = session_row(session_id=older_id, row_id="old-session")
    persistence.async_query_rows.side_effect = [
        [newer_slot, older_slot],
        [],
        [older_session],
        [slot_row(row_id="claimed-slot")],
    ]
    persistence.async_insert_row.side_effect = [
        {"ROWID": "claimed-slot"},
        {"ROWID": "new-session"},
    ]
    repository = CatalystAuthSessionRepository(persistence)

    await repository.create_session(
        session_id=SESSION_ID,
        user_id=USER_ID,
        refresh_token_hash=TOKEN_HASH,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        max_sessions=2,
    )

    assert [call.args for call in persistence.async_delete_row.await_args_list] == [
        (SLOTS_TABLE, "old-slot"),
        (SESSIONS_TABLE, "old-session"),
    ]


@pytest.mark.asyncio
async def test_rotation_claims_old_hash_before_updating_session():
    persistence = client()
    current = session_row()
    persistence.async_query_rows.side_effect = [[current], [slot_row()], [current]]
    persistence.async_insert_row.return_value = {"ROWID": "claim-row"}
    repository = CatalystAuthSessionRepository(persistence)

    rotated = await repository.rotate_session(
        session_id=SESSION_ID,
        supplied_token_hash=TOKEN_HASH,
        replacement_token_hash=NEW_TOKEN_HASH,
        now=NOW + timedelta(minutes=1),
    )

    assert rotated.refresh_token_hash == NEW_TOKEN_HASH
    assert persistence.async_insert_row.await_args.args[0] == CLAIMS_TABLE
    assert persistence.async_insert_row.await_args.args[1]["claim_hash"] == TOKEN_HASH
    assert persistence.async_update_row.await_args.args[0] == SESSIONS_TABLE


@pytest.mark.asyncio
async def test_old_token_reuse_revokes_the_session():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [session_row(token_hash=NEW_TOKEN_HASH)],
        [slot_row()],
    ]
    repository = CatalystAuthSessionRepository(persistence)

    with pytest.raises(SessionTokenRejected) as rejected:
        await repository.rotate_session(
            session_id=SESSION_ID,
            supplied_token_hash=TOKEN_HASH,
            replacement_token_hash="e" * 64,
            now=NOW + timedelta(minutes=2),
        )

    assert rejected.value.suspicious_reuse is True
    assert persistence.async_update_row.await_args.args[1]["revoked_at"]
    persistence.async_insert_row.assert_not_awaited()


@pytest.mark.asyncio
async def test_duplicate_atomic_claim_revokes_concurrent_rotation():
    persistence = client()
    current = session_row()
    persistence.async_query_rows.side_effect = [
        [current],
        [slot_row()],
        [{"ROWID": "existing-claim"}],
        [current],
    ]
    persistence.async_insert_row.side_effect = CatalystPersistenceError(
        "Catalyst row insert failed"
    )
    repository = CatalystAuthSessionRepository(persistence)

    with pytest.raises(SessionTokenRejected) as rejected:
        await repository.rotate_session(
            session_id=SESSION_ID,
            supplied_token_hash=TOKEN_HASH,
            replacement_token_hash=NEW_TOKEN_HASH,
            now=NOW + timedelta(minutes=1),
        )

    assert rejected.value.suspicious_reuse is True
    assert persistence.async_update_row.await_args.args[1]["revoked_at"]


@pytest.mark.asyncio
async def test_rotation_update_failure_leaves_token_claimed_and_fails_closed():
    persistence = client()
    current = session_row()
    persistence.async_query_rows.side_effect = [[current], [slot_row()], [current]]
    persistence.async_insert_row.return_value = {"ROWID": "claim-row"}
    persistence.async_update_row.side_effect = CatalystPersistenceError(
        "Catalyst row update failed"
    )
    repository = CatalystAuthSessionRepository(persistence)

    with pytest.raises(CatalystPersistenceError, match="row update failed"):
        await repository.rotate_session(
            session_id=SESSION_ID,
            supplied_token_hash=TOKEN_HASH,
            replacement_token_hash=NEW_TOKEN_HASH,
            now=NOW + timedelta(minutes=1),
        )

    persistence.async_insert_row.assert_awaited_once()
    persistence.async_delete_row.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoke_requires_the_current_token_hash():
    persistence = client()
    persistence.async_query_rows.side_effect = [[session_row()], [slot_row()]]
    repository = CatalystAuthSessionRepository(persistence)

    with pytest.raises(SessionTokenRejected) as rejected:
        await repository.revoke_session(
            session_id=SESSION_ID,
            supplied_token_hash=NEW_TOKEN_HASH,
            now=NOW,
        )

    assert rejected.value.suspicious_reuse is False
    persistence.async_update_row.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_session_removes_claims_slot_then_session():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [{"ROWID": "claim-one"}, {"ROWID": "claim-two"}],
        [session_row()],
        [slot_row()],
    ]
    repository = CatalystAuthSessionRepository(persistence)

    assert await repository.delete_session(SESSION_ID) is True

    assert [call.args for call in persistence.async_delete_row.await_args_list] == [
        (CLAIMS_TABLE, "claim-one"),
        (CLAIMS_TABLE, "claim-two"),
        (SLOTS_TABLE, "slot-row"),
        (SESSIONS_TABLE, "session-row"),
    ]
