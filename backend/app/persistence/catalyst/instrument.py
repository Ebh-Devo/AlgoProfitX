from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.bootstrap.instruments import EXCHANGES, INSTRUMENTS
from app.domain.enums import InstrumentType
from app.persistence.catalyst.paging import query_all
from app.persistence.catalyst.client import CatalystPersistenceClient, CatalystPersistenceError
from app.persistence.strategy import ExchangeSnapshotRecord, InstrumentSnapshotRecord


EXCHANGES_TABLE = "AlgoProfitXExchanges"
INSTRUMENTS_TABLE = "AlgoProfitXInstruments"
_SAFE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SAFE_ROWID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_EXCHANGE_COLUMNS = (
    "ROWID, exchange_uuid, code, name, country_code, timezone, "
    "default_currency, calendar_code, is_active, created_at, updated_at"
)
_INSTRUMENT_COLUMNS = (
    "ROWID, instrument_uuid, exchange_uuid, canonical_symbol, canonical_lookup, "
    "exchange_symbol, exchange_symbol_key, name, instrument_type, quote_currency, "
    "tick_size, lot_size, is_tradeable, isin, is_synthetic, is_active, "
    "created_at, updated_at"
)


def _literal(value: uuid.UUID) -> str:
    text = str(value)
    if not _SAFE_UUID.fullmatch(text):
        raise ValueError("Invalid Catalyst instrument ID")
    return f"'{text}'"


def _row_id(row: dict[str, Any]) -> str:
    value = str(row.get("ROWID", ""))
    if not _SAFE_ROWID.fullmatch(value):
        raise CatalystPersistenceError("Catalyst returned an invalid instrument row")
    return value


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Instrument timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CatalystPersistenceError("Catalyst returned an invalid instrument timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalystPersistenceError(
            "Catalyst returned an invalid instrument timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise CatalystPersistenceError("Catalyst returned an invalid instrument timestamp")
    return parsed.astimezone(timezone.utc)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    raise CatalystPersistenceError("Catalyst returned an invalid instrument boolean")


def _decimal(value: Any) -> Decimal | None:
    if value in {None, ""}:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise CatalystPersistenceError("Catalyst returned an invalid tick size") from exc
    if parsed <= 0:
        raise CatalystPersistenceError("Catalyst returned an invalid tick size")
    return parsed


class CatalystInstrumentRepository:
    """Catalyst-native public exchange and instrument catalog."""

    def __init__(self, client: CatalystPersistenceClient) -> None:
        self._client = client

    @staticmethod
    def _exchange(row: dict[str, Any]) -> ExchangeSnapshotRecord:
        _row_id(row)
        try:
            return ExchangeSnapshotRecord(
                id=uuid.UUID(str(row["exchange_uuid"])),
                code=str(row["code"]),
                name=str(row["name"]),
                country_code=str(row["country_code"]),
                timezone=str(row["timezone"]),
                default_currency=str(row["default_currency"]),
                calendar_code=str(row["calendar_code"]),
                is_active=_bool(row["is_active"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError(
                "Catalyst returned an invalid exchange row"
            ) from exc

    @staticmethod
    def _instrument(
        row: dict[str, Any], exchange: ExchangeSnapshotRecord
    ) -> InstrumentSnapshotRecord:
        _row_id(row)
        try:
            instrument_id = uuid.UUID(str(row["instrument_uuid"]))
            exchange_id = uuid.UUID(str(row["exchange_uuid"]))
            canonical = str(row["canonical_symbol"])
            exchange_symbol = str(row["exchange_symbol"])
            if exchange_id != exchange.id:
                raise ValueError
            if str(row["canonical_lookup"]) != _hash(canonical.casefold()):
                raise ValueError
            if str(row["exchange_symbol_key"]) != _hash(
                f"{exchange_id}:{exchange_symbol.casefold()}"
            ):
                raise ValueError
            lot_raw = row.get("lot_size")
            lot_size = int(lot_raw) if lot_raw not in {None, ""} else None
            tick_size = _decimal(row.get("tick_size"))
            is_tradeable = _bool(row["is_tradeable"])
            if is_tradeable and (tick_size is None or lot_size is None or lot_size <= 0):
                raise ValueError
            return InstrumentSnapshotRecord(
                id=instrument_id,
                exchange=exchange,
                canonical_symbol=canonical,
                exchange_symbol=exchange_symbol,
                name=str(row["name"]),
                instrument_type=InstrumentType(str(row["instrument_type"])),
                quote_currency=str(row["quote_currency"]),
                tick_size=tick_size,
                lot_size=lot_size,
                is_tradeable=is_tradeable,
                isin=str(row["isin"]) if row.get("isin") else None,
                is_synthetic=_bool(row["is_synthetic"]),
                is_active=_bool(row["is_active"]),
                created_at=_parse_time(row.get("created_at")),
                updated_at=_parse_time(row.get("updated_at")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError(
                "Catalyst returned an invalid instrument row"
            ) from exc

    async def _exchange_by_id(
        self, exchange_id: uuid.UUID
    ) -> ExchangeSnapshotRecord | None:
        rows = await self._client.async_query_rows(
            f"SELECT {_EXCHANGE_COLUMNS} FROM {EXCHANGES_TABLE} "
            f"WHERE exchange_uuid = {_literal(exchange_id)} LIMIT 1",
            EXCHANGES_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate exchanges")
        return self._exchange(rows[0])

    async def get_instrument(
        self, instrument_id: uuid.UUID
    ) -> InstrumentSnapshotRecord | None:
        rows = await self._client.async_query_rows(
            f"SELECT {_INSTRUMENT_COLUMNS} FROM {INSTRUMENTS_TABLE} "
            f"WHERE instrument_uuid = {_literal(instrument_id)} LIMIT 1",
            INSTRUMENTS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate instruments")
        try:
            exchange_id = uuid.UUID(str(rows[0]["exchange_uuid"]))
        except (KeyError, ValueError) as exc:
            raise CatalystPersistenceError(
                "Catalyst returned an invalid instrument row"
            ) from exc
        exchange = await self._exchange_by_id(exchange_id)
        if exchange is None:
            raise CatalystPersistenceError("Catalyst instrument exchange is missing")
        return self._instrument(rows[0], exchange)

    async def list_instruments(
        self,
        *,
        exchange_code: str | None,
        instrument_type: InstrumentType | None,
        symbol: str | None,
        search: str | None,
        is_tradeable: bool | None,
        is_active: bool,
        limit: int,
        offset: int,
    ) -> list[InstrumentSnapshotRecord]:
        rows = await query_all(
            self._client,
            f"SELECT {_INSTRUMENT_COLUMNS} FROM {INSTRUMENTS_TABLE}",
            INSTRUMENTS_TABLE,
        )
        exchanges: dict[uuid.UUID, ExchangeSnapshotRecord] = {}
        records: list[InstrumentSnapshotRecord] = []
        for row in rows:
            try:
                exchange_id = uuid.UUID(str(row["exchange_uuid"]))
            except (KeyError, ValueError) as exc:
                raise CatalystPersistenceError(
                    "Catalyst returned an invalid instrument row"
                ) from exc
            exchange = exchanges.get(exchange_id)
            if exchange is None:
                exchange = await self._exchange_by_id(exchange_id)
                if exchange is None:
                    raise CatalystPersistenceError("Catalyst instrument exchange is missing")
                exchanges[exchange_id] = exchange
            records.append(self._instrument(row, exchange))
        if exchange_code is not None:
            records = [item for item in records if item.exchange.code.casefold() == exchange_code.casefold()]
        if instrument_type is not None:
            records = [item for item in records if item.instrument_type is instrument_type]
        if symbol is not None:
            value = symbol.strip().casefold()
            records = [item for item in records if value in {item.canonical_symbol.casefold(), item.exchange_symbol.casefold()}]
        if search is not None:
            value = search.strip().casefold()
            records = [item for item in records if value in item.canonical_symbol.casefold() or value in item.exchange_symbol.casefold() or value in item.name.casefold()]
        if is_tradeable is not None:
            records = [item for item in records if item.is_tradeable is is_tradeable]
        records = [item for item in records if item.is_active is is_active and item.exchange.is_active]
        records.sort(key=lambda item: (item.exchange.code, item.exchange_symbol, str(item.id)))
        return records[offset : offset + limit]

    async def bootstrap_defaults(self) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        for seed in EXCHANGES:
            if await self._exchange_by_id(seed.id) is None:
                await self._client.async_insert_row(
                    EXCHANGES_TABLE,
                    {
                        "exchange_uuid": str(seed.id),
                        "code": seed.code,
                        "name": seed.name,
                        "country_code": seed.country_code,
                        "timezone": seed.timezone,
                        "default_currency": seed.default_currency,
                        "calendar_code": seed.calendar_code,
                        "is_active": True,
                        "created_at": _timestamp(now),
                        "updated_at": _timestamp(now),
                    },
                )
        for seed in INSTRUMENTS:
            if await self.get_instrument(seed.id) is None:
                payload: dict[str, Any] = {
                    "instrument_uuid": str(seed.id),
                    "exchange_uuid": str(seed.exchange_id),
                    "canonical_symbol": seed.canonical_symbol,
                    "canonical_lookup": _hash(seed.canonical_symbol.casefold()),
                    "exchange_symbol": seed.exchange_symbol,
                    "exchange_symbol_key": _hash(
                        f"{seed.exchange_id}:{seed.exchange_symbol.casefold()}"
                    ),
                    "name": seed.name,
                    "instrument_type": seed.instrument_type.value,
                    "quote_currency": seed.quote_currency,
                    "is_tradeable": seed.is_tradeable,
                    "is_synthetic": seed.is_synthetic,
                    "is_active": True,
                    "created_at": _timestamp(now),
                    "updated_at": _timestamp(now),
                }
                if seed.tick_size is not None:
                    payload["tick_size"] = str(seed.tick_size)
                if seed.lot_size is not None:
                    payload["lot_size"] = seed.lot_size
                await self._client.async_insert_row(
                    INSTRUMENTS_TABLE,
                    payload,
                )
        return len(EXCHANGES), len(INSTRUMENTS)
