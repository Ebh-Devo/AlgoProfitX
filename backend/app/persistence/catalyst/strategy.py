from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.strategy import StrategyStatus
from app.persistence.catalyst.client import (
    CatalystPersistenceClient,
    CatalystPersistenceError,
)
from app.persistence.strategy import DuplicateStrategySlug, StrategyRecord


STRATEGIES_TABLE = "AlgoProfitXStrategies"
_SAFE_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_SAFE_ROWID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_SAFE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_COLUMNS = (
    "ROWID, strategy_uuid, creator_uuid, name, slug, slug_lookup, description, "
    "status, is_public, current_version_uuid, created_at, updated_at, "
    "published_at, deployed_at"
)


def _literal(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid Catalyst {label}")
    return f"'{value}'"


def _slug_lookup(slug: str) -> str:
    return hashlib.sha256(slug.encode("ascii")).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Strategy timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: Any, label: str, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst strategy row has invalid {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalystPersistenceError(
            f"Catalyst strategy row has invalid {label}"
        ) from exc
    if parsed.tzinfo is None:
        raise CatalystPersistenceError(f"Catalyst strategy row has invalid {label}")
    return parsed.astimezone(timezone.utc)


def _parse_bool(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise CatalystPersistenceError(f"Catalyst strategy row has invalid {label}")


def _row_id(row: dict[str, Any]) -> str:
    value = str(row.get("ROWID", ""))
    if not _SAFE_ROWID.fullmatch(value):
        raise CatalystPersistenceError("Catalyst returned an invalid strategy row")
    return value


class CatalystStrategyRepository:
    """Catalyst strategy CRUD with UUID ownership and hashed slug lookups."""

    def __init__(self, client: CatalystPersistenceClient) -> None:
        self._client = client

    @staticmethod
    def _record(row: dict[str, Any]) -> StrategyRecord:
        _row_id(row)
        try:
            strategy_id = uuid.UUID(str(row["strategy_uuid"]))
            creator_id = uuid.UUID(str(row["creator_uuid"]))
            name = str(row["name"])
            slug = str(row["slug"])
            status = StrategyStatus(str(row["status"]))
            lookup = str(row["slug_lookup"])
            current_raw = row.get("current_version_uuid")
            current_id = uuid.UUID(str(current_raw)) if current_raw else None
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError(
                "Catalyst returned an invalid strategy row"
            ) from exc
        if (
            not name
            or not _SAFE_SLUG.fullmatch(slug)
            or lookup != _slug_lookup(slug)
        ):
            raise CatalystPersistenceError("Catalyst returned an invalid strategy row")
        created = _parse_timestamp(row.get("created_at"), "creation time")
        updated = _parse_timestamp(row.get("updated_at"), "update time")
        assert created is not None and updated is not None
        description = row.get("description")
        if description is not None and not isinstance(description, str):
            raise CatalystPersistenceError("Catalyst strategy row has invalid description")
        return StrategyRecord(
            id=strategy_id,
            creator_id=creator_id,
            name=name,
            slug=slug,
            description=description,
            status=status,
            is_public=_parse_bool(row.get("is_public"), "visibility"),
            current_version_id=current_id,
            created_at=created,
            updated_at=updated,
            published_at=_parse_timestamp(
                row.get("published_at"), "publication time", optional=True
            ),
            deployed_at=_parse_timestamp(
                row.get("deployed_at"), "deployment time", optional=True
            ),
        )

    async def _by_slug(self, slug: str) -> StrategyRecord | None:
        lookup = _slug_lookup(slug)
        literal = _literal(lookup, _SAFE_HEX, "strategy slug lookup")
        rows = await self._client.async_query_rows(
            f"SELECT {_COLUMNS} FROM {STRATEGIES_TABLE} "
            f"WHERE slug_lookup = {literal} LIMIT 1",
            STRATEGIES_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate strategies")
        _row_id(rows[0])
        return self._record(rows[0])

    async def _owned_row(
        self, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> dict[str, Any] | None:
        strategy_literal = _literal(str(strategy_id), _SAFE_UUID, "strategy ID")
        creator_literal = _literal(str(creator_id), _SAFE_UUID, "creator ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_COLUMNS} FROM {STRATEGIES_TABLE} "
            f"WHERE strategy_uuid = {strategy_literal} "
            f"AND creator_uuid = {creator_literal} LIMIT 1",
            STRATEGIES_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate strategies")
        _row_id(rows[0])
        return rows[0]

    async def create_strategy(
        self, *, creator_id: uuid.UUID, name: str, slug: str, description: str | None
    ) -> StrategyRecord:
        if not 3 <= len(name) <= 150 or not _SAFE_SLUG.fullmatch(slug):
            raise ValueError("Invalid strategy")
        if len(slug) > 180 or (description is not None and len(description) > 10000):
            raise ValueError("Invalid strategy")
        if await self._by_slug(slug) is not None:
            raise DuplicateStrategySlug("Strategy slug is already in use")
        now = datetime.now(timezone.utc)
        row: dict[str, Any] = {
            "strategy_uuid": str(uuid.uuid4()),
            "creator_uuid": str(creator_id),
            "name": name,
            "slug": slug,
            "slug_lookup": _slug_lookup(slug),
            "status": StrategyStatus.DRAFT.value,
            "is_public": False,
            "created_at": _timestamp(now),
            "updated_at": _timestamp(now),
        }
        if description is not None:
            row["description"] = description
        try:
            inserted = await self._client.async_insert_row(STRATEGIES_TABLE, row)
        except CatalystPersistenceError:
            if await self._by_slug(slug) is not None:
                raise DuplicateStrategySlug("Strategy slug is already in use") from None
            raise
        return self._record({**row, **inserted})

    async def list_strategies(self, creator_id: uuid.UUID) -> list[StrategyRecord]:
        creator_literal = _literal(str(creator_id), _SAFE_UUID, "creator ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_COLUMNS} FROM {STRATEGIES_TABLE} "
            f"WHERE creator_uuid = {creator_literal}",
            STRATEGIES_TABLE,
        )
        return sorted(
            (self._record(row) for row in rows),
            key=lambda strategy: strategy.created_at,
            reverse=True,
        )

    async def get_strategy(
        self, *, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> StrategyRecord | None:
        row = await self._owned_row(strategy_id, creator_id)
        return self._record(row) if row is not None else None

    async def update_strategy(
        self,
        *,
        strategy_id: uuid.UUID,
        creator_id: uuid.UUID,
        updates: dict[str, object],
    ) -> StrategyRecord | None:
        row = await self._owned_row(strategy_id, creator_id)
        if row is None:
            return None
        allowed = {"name", "slug", "description"}
        if not updates.keys() <= allowed:
            raise ValueError("Invalid strategy update")
        payload: dict[str, Any] = {"ROWID": _row_id(row)}
        if "name" in updates:
            name = updates["name"]
            if not isinstance(name, str) or not 3 <= len(name) <= 150:
                raise ValueError("Invalid strategy")
            payload["name"] = name
        if "description" in updates:
            description = updates["description"]
            if description is not None and (
                not isinstance(description, str) or len(description) > 10000
            ):
                raise ValueError("Invalid strategy")
            payload["description"] = description
        if "slug" in updates:
            slug = updates["slug"]
            if (
                not isinstance(slug, str)
                or len(slug) > 180
                or not _SAFE_SLUG.fullmatch(slug)
            ):
                raise ValueError("Invalid strategy")
            existing = await self._by_slug(slug)
            if existing is not None and existing.id != strategy_id:
                raise DuplicateStrategySlug("Strategy slug is already in use")
            payload["slug"] = slug
            payload["slug_lookup"] = _slug_lookup(slug)
        payload["updated_at"] = _timestamp(datetime.now(timezone.utc))
        try:
            await self._client.async_update_row(STRATEGIES_TABLE, payload)
        except CatalystPersistenceError:
            slug = payload.get("slug")
            if isinstance(slug, str):
                existing = await self._by_slug(slug)
                if existing is not None and existing.id != strategy_id:
                    raise DuplicateStrategySlug(
                        "Strategy slug is already in use"
                    ) from None
            raise
        return self._record({**row, **payload})

    async def delete_strategy(
        self, *, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> bool:
        row = await self._owned_row(strategy_id, creator_id)
        if row is None:
            return False
        record = self._record(row)
        if record.status is not StrategyStatus.DRAFT:
            raise ValueError("Only an unused draft strategy can be deleted")
        await self._client.async_delete_row(STRATEGIES_TABLE, _row_id(row))
        return True
