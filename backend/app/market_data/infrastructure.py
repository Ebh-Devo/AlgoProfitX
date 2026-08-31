import hashlib
import asyncio
import logging
import json
import math
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from app.core.metrics import metrics
from app.core.observability import log_event
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.contracts import Candle, HistoricalMarketDataProvider
from app.models.instrument import InstrumentVendorMapping

ERROR_CODES = frozenset({
    "market_data_mapping_missing", "market_data_mapping_expired", "market_data_provider_unavailable",
    "market_data_auth_missing", "market_data_auth_failed", "market_data_rate_limited", "market_data_timeout",
    "market_data_not_found", "market_data_invalid_payload", "market_data_partial_coverage", "market_data_checksum_mismatch",
})


class MarketDataError(Exception):
    def __init__(self, code: str, message: str):
        if code not in ERROR_CODES:
            code = "market_data_invalid_payload"
        self.code = code
        super().__init__(message)


class ProviderRegistry:
    def __init__(self, providers: Iterable[HistoricalMarketDataProvider] = ()):
        self._providers = {provider.code: provider for provider in providers}

    def resolve(self, code: str) -> HistoricalMarketDataProvider:
        provider = self._providers.get(code)
        if provider is None:
            raise MarketDataError("market_data_provider_unavailable", "Configured market data provider is unavailable")
        return provider


async def resolve_mapping(session: AsyncSession, instrument_id, provider_code: str, start: date, end: date) -> InstrumentVendorMapping:
    rows = list((await session.scalars(select(InstrumentVendorMapping).where(
        InstrumentVendorMapping.instrument_id == instrument_id,
        InstrumentVendorMapping.provider_code == provider_code,
        InstrumentVendorMapping.is_active.is_(True),
    ))).all())
    if not rows:
        raise MarketDataError("market_data_mapping_missing", "Instrument mapping is missing for configured provider")
    applicable = [row for row in rows if (row.valid_from is None or row.valid_from <= start) and (row.valid_to is None or row.valid_to >= end)]
    if not applicable:
        raise MarketDataError("market_data_mapping_expired", "Instrument mapping is not valid for requested range")
    if len(applicable) != 1:
        raise MarketDataError("market_data_invalid_payload", "Instrument mapping is ambiguous for requested range")
    return applicable[0]


def validate_and_normalize(candles: Iterable[Candle], *, start: date, end: date, max_candles: int) -> tuple[tuple[Candle, ...], int]:
    by_date: dict[date, Candle] = {}
    duplicates = 0
    for candle in candles:
        if candle.timestamp.tzinfo is None or candle.timestamp.utcoffset() is None:
            raise MarketDataError("market_data_invalid_payload", "Market data timestamp must be timezone-aware")
        timestamp = candle.timestamp.astimezone(timezone.utc)
        if not start <= candle.session_date <= end:
            raise MarketDataError("market_data_invalid_payload", "Market data row is outside requested mapping range")
        prices = tuple(_decimal(x) for x in (candle.open, candle.high, candle.low, candle.close))
        if any(x <= 0 for x in prices):
            raise MarketDataError("market_data_invalid_payload", "Market data prices must be positive")
        o, h, l, c = prices
        if h < max(o, c, l) or l > min(o, c, h):
            raise MarketDataError("market_data_invalid_payload", "Market data OHLC relationship is invalid")
        if candle.volume is not None and (not isinstance(candle.volume, int) or candle.volume < 0):
            raise MarketDataError("market_data_invalid_payload", "Market data volume must be a non-negative integer or missing")
        normalized = Candle(candle.session_date, timestamp, o, h, l, c, candle.volume)
        existing = by_date.get(candle.session_date)
        if existing is not None:
            if existing != normalized:
                raise MarketDataError("market_data_invalid_payload", "Market data contains conflicting duplicate sessions")
            duplicates += 1
        else:
            by_date[candle.session_date] = normalized
    result = tuple(by_date[key] for key in sorted(by_date))
    if not result:
        raise MarketDataError("market_data_not_found", "Market data contains no candles")
    if len(result) > max_candles:
        raise MarketDataError("market_data_invalid_payload", "Market data candle count exceeds configured limit")
    return result, duplicates


def _decimal(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MarketDataError("market_data_invalid_payload", "Market data price is invalid") from exc
    if not result.is_finite() or not math.isfinite(float(result)):
        raise MarketDataError("market_data_invalid_payload", "Market data price is non-finite")
    return result


def canonical_serialization(candles: Iterable[Candle]) -> bytes:
    rows = [{
        "session_date": c.session_date.isoformat(), "timestamp": c.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "open": _canonical_decimal(c.open), "high": _canonical_decimal(c.high), "low": _canonical_decimal(c.low), "close": _canonical_decimal(c.close), "volume": c.volume,
    } for c in candles]
    return json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _canonical_decimal(value: Decimal) -> str:
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def canonical_checksum(candles: Iterable[Candle]) -> str:
    return hashlib.sha256(canonical_serialization(candles)).hexdigest()


def dataset_key(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode()).hexdigest()


async def load_with_policy(provider, request, *, timeout_seconds: float, max_retries: int):
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.wait_for(provider.load(request), timeout=timeout_seconds)
        except TimeoutError as exc:
            if attempt >= max_retries:
                provider_code = str(getattr(provider, "code", "unknown"))
                log_event("market_data_provider_failed", level=logging.WARNING, provider_code=provider_code, error_code="market_data_timeout")
                metrics.increment("market_data.failures", tags={"provider": provider_code, "error_code": "market_data_timeout"})
                raise MarketDataError("market_data_timeout", "Market data provider timed out") from exc
