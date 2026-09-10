from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.instrument import InstrumentType
from app.models.strategy import StrategyStatus
from app.persistence.catalyst.client import (
    CatalystPersistenceClient,
    CatalystPersistenceError,
)
from app.persistence.strategy import (
    DuplicateStrategySlug,
    ExchangeSnapshotRecord,
    InstrumentSnapshotRecord,
    StrategyRecord,
    StrategyVersionRecord,
)


STRATEGIES_TABLE = "AlgoProfitXStrategies"
STRATEGY_VERSIONS_TABLE = "AlgoProfitXStrategyVersions"
STRATEGY_LOCKS_TABLE = "AlgoProfitXStrategyLocks"
_LOCK_TTL = timedelta(seconds=30)
_LOCK_ATTEMPTS = 4
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
_VERSION_COLUMNS = (
    "ROWID, version_uuid, strategy_uuid, version_key, instrument_uuid, "
    "version_number, configuration, backtest_configuration, "
    "instrument_snapshot, created_at"
)
_LOCK_COLUMNS = "ROWID, strategy_uuid, owner_token, acquired_at"


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


def _bounded_json(value: dict[str, Any], label: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > 10000:
        raise ValueError(f"{label} is too large")
    return encoded


def _parse_json(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst version row has invalid {label}")
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise CatalystPersistenceError(
            f"Catalyst version row has invalid {label}"
        ) from exc
    if not isinstance(parsed, dict):
        raise CatalystPersistenceError(f"Catalyst version row has invalid {label}")
    return parsed


def _version_key(strategy_id: uuid.UUID, version_number: int) -> str:
    return hashlib.sha256(f"{strategy_id}:{version_number}".encode("ascii")).hexdigest()


def _decimal(value: Any, label: str) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CatalystPersistenceError(
            f"Catalyst version row has invalid {label}"
        ) from exc


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
    def _instrument_payload(instrument: InstrumentSnapshotRecord) -> dict[str, Any]:
        return {
            "id": str(instrument.id),
            "exchange": {
                "id": str(instrument.exchange.id),
                "code": instrument.exchange.code,
                "name": instrument.exchange.name,
                "country_code": instrument.exchange.country_code,
                "timezone": instrument.exchange.timezone,
                "default_currency": instrument.exchange.default_currency,
                "calendar_code": instrument.exchange.calendar_code,
                "is_active": instrument.exchange.is_active,
            },
            "canonical_symbol": instrument.canonical_symbol,
            "exchange_symbol": instrument.exchange_symbol,
            "name": instrument.name,
            "instrument_type": instrument.instrument_type.value,
            "quote_currency": instrument.quote_currency,
            "tick_size": str(instrument.tick_size) if instrument.tick_size is not None else None,
            "lot_size": instrument.lot_size,
            "is_tradeable": instrument.is_tradeable,
            "isin": instrument.isin,
            "is_synthetic": instrument.is_synthetic,
            "is_active": instrument.is_active,
            "created_at": _timestamp(instrument.created_at),
            "updated_at": _timestamp(instrument.updated_at),
        }

    @staticmethod
    def _instrument_record(value: dict[str, Any]) -> InstrumentSnapshotRecord:
        try:
            exchange_value = value["exchange"]
            if not isinstance(exchange_value, dict):
                raise TypeError
            created_at = _parse_timestamp(value.get("created_at"), "instrument creation time")
            updated_at = _parse_timestamp(value.get("updated_at"), "instrument update time")
            assert created_at is not None and updated_at is not None
            exchange = ExchangeSnapshotRecord(
                id=uuid.UUID(str(exchange_value["id"])),
                code=str(exchange_value["code"]),
                name=str(exchange_value["name"]),
                country_code=str(exchange_value["country_code"]),
                timezone=str(exchange_value["timezone"]),
                default_currency=str(exchange_value["default_currency"]),
                calendar_code=str(exchange_value["calendar_code"]),
                is_active=_parse_bool(exchange_value["is_active"], "exchange activity"),
            )
            return InstrumentSnapshotRecord(
                id=uuid.UUID(str(value["id"])),
                exchange=exchange,
                canonical_symbol=str(value["canonical_symbol"]),
                exchange_symbol=str(value["exchange_symbol"]),
                name=str(value["name"]),
                instrument_type=InstrumentType(str(value["instrument_type"])),
                quote_currency=str(value["quote_currency"]),
                tick_size=_decimal(value.get("tick_size"), "tick size"),
                lot_size=int(value["lot_size"]) if value.get("lot_size") is not None else None,
                is_tradeable=_parse_bool(value["is_tradeable"], "tradeability"),
                isin=str(value["isin"]) if value.get("isin") is not None else None,
                is_synthetic=_parse_bool(value["is_synthetic"], "synthetic status"),
                is_active=_parse_bool(value["is_active"], "instrument activity"),
                created_at=created_at,
                updated_at=updated_at,
            )
        except (AssertionError, KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError(
                "Catalyst version row has invalid instrument snapshot"
            ) from exc

    @classmethod
    def _version_record(cls, row: dict[str, Any]) -> StrategyVersionRecord:
        _row_id(row)
        try:
            version_id = uuid.UUID(str(row["version_uuid"]))
            strategy_id = uuid.UUID(str(row["strategy_uuid"]))
            instrument_id = uuid.UUID(str(row["instrument_uuid"]))
            version_number = int(row["version_number"])
            key = str(row["version_key"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError("Catalyst returned an invalid version row") from exc
        if version_number < 1 or key != _version_key(strategy_id, version_number):
            raise CatalystPersistenceError("Catalyst returned an invalid version row")
        created_at = _parse_timestamp(row.get("created_at"), "version creation time")
        assert created_at is not None
        snapshot = cls._instrument_record(
            _parse_json(row.get("instrument_snapshot"), "instrument snapshot")
        )
        if snapshot.id != instrument_id:
            raise CatalystPersistenceError("Catalyst version row has invalid instrument snapshot")
        return StrategyVersionRecord(
            id=version_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            instrument=snapshot,
            version_number=version_number,
            configuration=_parse_json(row.get("configuration"), "configuration"),
            backtest_configuration=_parse_json(
                row.get("backtest_configuration"), "backtest configuration"
            ),
            created_at=created_at,
        )

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
        if await self._version_rows(strategy_id):
            raise ValueError("Only an unused draft strategy can be deleted")
        await self._client.async_delete_row(STRATEGIES_TABLE, _row_id(row))
        return True

    async def _version_rows(self, strategy_id: uuid.UUID) -> list[dict[str, Any]]:
        strategy_literal = _literal(str(strategy_id), _SAFE_UUID, "strategy ID")
        return await self._client.async_query_rows(
            f"SELECT {_VERSION_COLUMNS} FROM {STRATEGY_VERSIONS_TABLE} "
            f"WHERE strategy_uuid = {strategy_literal}",
            STRATEGY_VERSIONS_TABLE,
        )

    async def _version_by_id(
        self, strategy_id: uuid.UUID, version_id: uuid.UUID
    ) -> dict[str, Any] | None:
        strategy_literal = _literal(str(strategy_id), _SAFE_UUID, "strategy ID")
        version_literal = _literal(str(version_id), _SAFE_UUID, "version ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_VERSION_COLUMNS} FROM {STRATEGY_VERSIONS_TABLE} "
            f"WHERE strategy_uuid = {strategy_literal} "
            f"AND version_uuid = {version_literal} LIMIT 1",
            STRATEGY_VERSIONS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate versions")
        return rows[0]

    async def _lock_row(self, strategy_id: uuid.UUID) -> dict[str, Any] | None:
        literal = _literal(str(strategy_id), _SAFE_UUID, "strategy ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_LOCK_COLUMNS} FROM {STRATEGY_LOCKS_TABLE} "
            f"WHERE strategy_uuid = {literal} LIMIT 1",
            STRATEGY_LOCKS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate strategy locks")
        _row_id(rows[0])
        return rows[0]

    @asynccontextmanager
    async def _strategy_lock(self, strategy_id: uuid.UUID):
        owner_token = secrets.token_hex(32)
        acquired = False
        for _ in range(_LOCK_ATTEMPTS):
            now = datetime.now(timezone.utc)
            try:
                await self._client.async_insert_row(
                    STRATEGY_LOCKS_TABLE,
                    {
                        "strategy_uuid": str(strategy_id),
                        "owner_token": owner_token,
                        "acquired_at": _timestamp(now),
                    },
                )
                acquired = True
                break
            except CatalystPersistenceError:
                existing = await self._lock_row(strategy_id)
                if existing is None:
                    continue
                acquired_at = _parse_timestamp(existing.get("acquired_at"), "lock time")
                assert acquired_at is not None
                if now - acquired_at <= _LOCK_TTL:
                    raise ValueError("Strategy is being updated; retry the request") from None
                await self._client.async_delete_row(
                    STRATEGY_LOCKS_TABLE, _row_id(existing)
                )
        if not acquired:
            raise ValueError("Strategy is being updated; retry the request")
        try:
            yield
        finally:
            existing = await self._lock_row(strategy_id)
            if existing is not None and existing.get("owner_token") == owner_token:
                await self._client.async_delete_row(
                    STRATEGY_LOCKS_TABLE, _row_id(existing)
                )

    async def create_version(
        self,
        *,
        strategy_id: uuid.UUID,
        creator_id: uuid.UUID,
        instrument: InstrumentSnapshotRecord,
        configuration: dict[str, Any],
        backtest_configuration: dict[str, Any],
    ) -> StrategyVersionRecord:
        if await self._owned_row(strategy_id, creator_id) is None:
            raise ValueError("Strategy not found")
        configuration_json = _bounded_json(configuration, "configuration")
        backtest_json = _bounded_json(
            backtest_configuration, "backtest_configuration"
        )
        snapshot_json = _bounded_json(
            self._instrument_payload(instrument), "instrument snapshot"
        )
        async with self._strategy_lock(strategy_id):
            if await self._owned_row(strategy_id, creator_id) is None:
                raise ValueError("Strategy not found")
            rows = await self._version_rows(strategy_id)
            version_number = max(
                (self._version_record(row).version_number for row in rows), default=0
            ) + 1
            now = datetime.now(timezone.utc)
            payload: dict[str, Any] = {
                "version_uuid": str(uuid.uuid4()),
                "strategy_uuid": str(strategy_id),
                "version_key": _version_key(strategy_id, version_number),
                "instrument_uuid": str(instrument.id),
                "version_number": version_number,
                "configuration": configuration_json,
                "backtest_configuration": backtest_json,
                "instrument_snapshot": snapshot_json,
                "created_at": _timestamp(now),
            }
            inserted = await self._client.async_insert_row(
                STRATEGY_VERSIONS_TABLE, payload
            )
            return self._version_record({**payload, **inserted})

    async def list_versions(
        self, *, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> list[StrategyVersionRecord]:
        if await self._owned_row(strategy_id, creator_id) is None:
            return []
        return sorted(
            (self._version_record(row) for row in await self._version_rows(strategy_id)),
            key=lambda version: version.version_number,
        )

    async def get_version(
        self,
        *,
        strategy_id: uuid.UUID,
        version_id: uuid.UUID,
        creator_id: uuid.UUID,
    ) -> StrategyVersionRecord | None:
        if await self._owned_row(strategy_id, creator_id) is None:
            return None
        row = await self._version_by_id(strategy_id, version_id)
        return self._version_record(row) if row is not None else None

    async def delete_version(self, version_id: uuid.UUID) -> bool:
        literal = _literal(str(version_id), _SAFE_UUID, "version ID")
        rows = await self._client.async_query_rows(
            f"SELECT ROWID FROM {STRATEGY_VERSIONS_TABLE} "
            f"WHERE version_uuid = {literal} LIMIT 1",
            STRATEGY_VERSIONS_TABLE,
        )
        if not rows:
            return False
        await self._client.async_delete_row(STRATEGY_VERSIONS_TABLE, _row_id(rows[0]))
        return True

    async def cleanup_probe_strategy(
        self, *, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> bool:
        """Remove a probe aggregate after the caller's Development-only guard."""
        for row in await self._version_rows(strategy_id):
            await self._client.async_delete_row(
                STRATEGY_VERSIONS_TABLE, _row_id(row)
            )
        row = await self._owned_row(strategy_id, creator_id)
        if row is None:
            return False
        await self._client.async_delete_row(STRATEGIES_TABLE, _row_id(row))
        return True

    async def transition_strategy(
        self,
        *,
        strategy_id: uuid.UUID,
        creator_id: uuid.UUID,
        target: StrategyStatus,
    ) -> StrategyRecord | None:
        allowed = {
            StrategyStatus.DRAFT: {StrategyStatus.PUBLISHED, StrategyStatus.ARCHIVED},
            StrategyStatus.PUBLISHED: {StrategyStatus.DEPLOYED, StrategyStatus.ARCHIVED},
            StrategyStatus.DEPLOYED: {StrategyStatus.ARCHIVED},
            StrategyStatus.ARCHIVED: set(),
        }
        async with self._strategy_lock(strategy_id):
            row = await self._owned_row(strategy_id, creator_id)
            if row is None:
                return None
            record = self._record(row)
            if target not in allowed[record.status]:
                raise ValueError(
                    "Invalid strategy lifecycle transition: "
                    f"{record.status.value} -> {target.value}"
                )
            now = datetime.now(timezone.utc)
            payload: dict[str, Any] = {
                "ROWID": _row_id(row),
                "status": target.value,
                "updated_at": _timestamp(now),
            }
            if target is StrategyStatus.PUBLISHED:
                versions = sorted(
                    (self._version_record(item) for item in await self._version_rows(strategy_id)),
                    key=lambda version: version.version_number,
                )
                if not versions:
                    raise ValueError("A strategy version is required before publishing")
                payload.update(
                    {
                        "current_version_uuid": str(versions[-1].id),
                        "is_public": True,
                        "published_at": _timestamp(now),
                    }
                )
            elif target is StrategyStatus.DEPLOYED:
                payload["deployed_at"] = _timestamp(now)
            elif target is StrategyStatus.ARCHIVED:
                payload["is_public"] = False
            await self._client.async_update_row(STRATEGIES_TABLE, payload)
            return self._record({**row, **payload})
