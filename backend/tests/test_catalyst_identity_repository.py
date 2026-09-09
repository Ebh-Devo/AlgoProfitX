import hashlib
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.persistence.catalyst.client import CatalystPersistenceError
from app.persistence.catalyst.identity import (
    CatalystIdentityRepository,
    ROLES_TABLE,
    USERS_TABLE,
)
from app.persistence.identity import DuplicateIdentityError


def user_row(*, roles: list[str] | None = None) -> dict[str, object]:
    return {
        "ROWID": "36851000000000001",
        "user_uuid": "11111111-1111-4111-8111-111111111111",
        "email": "person@example.com",
        "password_hash": "$argon2id$stored-hash",
        "is_active": True,
        "is_verified": False,
        "role_names": json.dumps(roles or ["INVESTOR"]),
        "full_name": "Example Person",
        "phone": None,
        "created_at": "2026-09-09T06:30:00+00:00",
        "updated_at": "2026-09-09T06:30:00+00:00",
    }


def client() -> SimpleNamespace:
    return SimpleNamespace(
        async_query_rows=AsyncMock(),
        async_insert_row=AsyncMock(),
        async_update_row=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_email_lookup_never_puts_user_text_in_zcql():
    persistence = client()
    persistence.async_query_rows.return_value = [user_row()]
    repository = CatalystIdentityRepository(persistence)

    result = await repository.get_user_by_email("Person@Example.com")

    assert result is not None
    assert result.email == "person@example.com"
    query, table = persistence.async_query_rows.await_args.args
    assert table == USERS_TABLE
    assert "Person@Example.com" not in query
    assert "person@example.com" not in query
    assert hashlib.sha256(b"person@example.com").hexdigest() in query


@pytest.mark.asyncio
async def test_registration_is_one_user_insert_with_embedded_default_role():
    persistence = client()
    persistence.async_query_rows.side_effect = [[{"ROWID": "role"}], []]
    persistence.async_insert_row.return_value = {"ROWID": "user"}
    repository = CatalystIdentityRepository(persistence)

    result = await repository.register_user(
        email="Person@Example.com",
        password_hash="$argon2id$stored-hash",
        full_name="Example Person",
    )

    assert result.email == "person@example.com"
    assert [role.name for role in result.roles] == ["INVESTOR"]
    table, row = persistence.async_insert_row.await_args.args
    assert table == USERS_TABLE
    assert row["email"] == "person@example.com"
    assert row["password_hash"] == "$argon2id$stored-hash"
    assert json.loads(row["role_names"]) == ["INVESTOR"]
    assert uuid.UUID(row["user_uuid"])
    assert row["created_at"] == row["updated_at"]


@pytest.mark.asyncio
async def test_registration_rejects_existing_email_before_insert():
    persistence = client()
    persistence.async_query_rows.side_effect = [[{"ROWID": "role"}], [user_row()]]
    repository = CatalystIdentityRepository(persistence)

    with pytest.raises(DuplicateIdentityError, match="already registered"):
        await repository.register_user(
            email="person@example.com",
            password_hash="$argon2id$stored-hash",
            full_name=None,
        )

    persistence.async_insert_row.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_unique_race_is_classified_only_after_confirming_duplicate():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [{"ROWID": "role"}],
        [],
        [user_row()],
    ]
    persistence.async_insert_row.side_effect = CatalystPersistenceError(
        "Catalyst row insert failed"
    )
    repository = CatalystIdentityRepository(persistence)

    with pytest.raises(DuplicateIdentityError, match="already registered"):
        await repository.register_user(
            email="person@example.com",
            password_hash="$argon2id$stored-hash",
            full_name=None,
        )


@pytest.mark.asyncio
async def test_non_duplicate_insert_failure_remains_sanitized_persistence_error():
    persistence = client()
    persistence.async_query_rows.side_effect = [[{"ROWID": "role"}], [], []]
    persistence.async_insert_row.side_effect = CatalystPersistenceError(
        "Catalyst row insert failed"
    )
    repository = CatalystIdentityRepository(persistence)

    with pytest.raises(CatalystPersistenceError, match="row insert failed"):
        await repository.register_user(
            email="person@example.com",
            password_hash="$argon2id$stored-hash",
            full_name=None,
        )


@pytest.mark.asyncio
async def test_creator_enrollment_is_idempotent():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [{"ROWID": "role"}],
        [user_row(roles=["CREATOR", "INVESTOR"])],
    ]
    repository = CatalystIdentityRepository(persistence)

    result = await repository.enroll_creator(
        uuid.UUID("11111111-1111-4111-8111-111111111111")
    )

    assert [role.name for role in result.roles] == ["CREATOR", "INVESTOR"]
    persistence.async_update_row.assert_not_awaited()


@pytest.mark.asyncio
async def test_creator_enrollment_adds_role_without_exposing_rowid():
    persistence = client()
    persistence.async_query_rows.side_effect = [
        [{"ROWID": "role"}],
        [user_row()],
    ]
    persistence.async_update_row.return_value = {"ROWID": "user"}
    repository = CatalystIdentityRepository(persistence)

    result = await repository.enroll_creator(
        uuid.UUID("11111111-1111-4111-8111-111111111111")
    )

    assert result.id == uuid.UUID("11111111-1111-4111-8111-111111111111")
    assert [role.name for role in result.roles] == ["CREATOR", "INVESTOR"]
    table, update = persistence.async_update_row.await_args.args
    assert table == USERS_TABLE
    assert update["ROWID"] == "36851000000000001"
    assert json.loads(update["role_names"]) == ["CREATOR", "INVESTOR"]


@pytest.mark.asyncio
async def test_role_catalog_queries_use_only_fixed_role_names():
    persistence = client()
    persistence.async_query_rows.return_value = []
    repository = CatalystIdentityRepository(persistence)

    with pytest.raises(RuntimeError, match="Default user role"):
        await repository.register_user(
            email="person@example.com",
            password_hash="$argon2id$stored-hash",
            full_name=None,
        )

    query, table = persistence.async_query_rows.await_args.args
    assert table == ROLES_TABLE
    assert "INVESTOR" in query


@pytest.mark.asyncio
async def test_delete_user_uses_internal_rowid_and_reports_missing_user():
    persistence = client()
    persistence.async_delete_row = AsyncMock()
    persistence.async_query_rows.side_effect = [
        [{"ROWID": "36851000000408776"}],
        [],
    ]
    repository = CatalystIdentityRepository(persistence)
    user_id = uuid.UUID("11111111-1111-4111-8111-111111111111")

    assert await repository.delete_user(user_id) is True
    persistence.async_delete_row.assert_awaited_once_with(
        USERS_TABLE, "36851000000408776"
    )
    assert await repository.delete_user(user_id) is False
