from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
import uuid

import pytest

from app.backtesting.contracts import Candle
from app.market_data.infrastructure import MarketDataError, ProviderRegistry, canonical_checksum, load_with_policy, resolve_mapping, validate_and_normalize
from app.models.instrument import InstrumentVendorMapping


def candle(day=1, *, open="100", high="110", low="90", close="105", volume=0):
    return Candle(date(2025, 1, day), datetime(2025, 1, day, 10, tzinfo=timezone.utc), Decimal(open), Decimal(high), Decimal(low), Decimal(close), volume)


def test_daily_normalization_preserves_zero_and_missing_volume_and_collapses_exact_duplicates():
    first = candle(volume=0)
    second = candle(2, volume=None)
    rows, duplicates = validate_and_normalize([second, first, first], start=date(2025, 1, 1), end=date(2025, 1, 2), max_candles=2)
    assert [row.volume for row in rows] == [0, None]
    assert duplicates == 1
    assert canonical_checksum(rows) == canonical_checksum(tuple(reversed(tuple(reversed(rows)))))


@pytest.mark.parametrize("row", [
    candle(open="0"), candle(high="99"), candle(low="106"), candle(volume=-1),
    candle(open="NaN"), Candle(date(2025, 1, 1), datetime(2025, 1, 1, 10), Decimal("100"), Decimal("110"), Decimal("90"), Decimal("105"), 1),
])
def test_invalid_daily_payloads_are_rejected(row):
    with pytest.raises(MarketDataError, match="Market data"):
        validate_and_normalize([row], start=date(2025, 1, 1), end=date(2025, 1, 2), max_candles=2)


def test_conflicting_duplicates_and_out_of_range_rows_fail():
    with pytest.raises(MarketDataError, match="conflicting"):
        validate_and_normalize([candle(), candle(close="106")], start=date(2025, 1, 1), end=date(2025, 1, 1), max_candles=2)
    with pytest.raises(MarketDataError, match="outside"):
        validate_and_normalize([candle(2)], start=date(2025, 1, 1), end=date(2025, 1, 1), max_candles=2)


def test_provider_registry_has_stable_sanitized_failure():
    with pytest.raises(MarketDataError) as raised:
        ProviderRegistry().resolve("unconfigured")
    assert raised.value.code == "market_data_provider_unavailable"


@pytest.mark.parametrize("code", ["market_data_rate_limited", "market_data_timeout", "market_data_auth_failed"])
def test_provider_failure_codes_are_stable(code):
    assert MarketDataError(code, "sanitized provider failure").code == code


class _Rows:
    def __init__(self, rows): self.rows = rows
    def all(self): return self.rows


@pytest.mark.asyncio
async def test_mapping_resolution_rejects_missing_expired_and_ambiguous_mappings():
    instrument_id = uuid.uuid4()
    session = AsyncMock()
    session.scalars.return_value = _Rows([])
    with pytest.raises(MarketDataError) as missing:
        await resolve_mapping(session, instrument_id, "future-provider", date(2025, 1, 1), date(2025, 1, 31))
    assert missing.value.code == "market_data_mapping_missing"
    expired = InstrumentVendorMapping(instrument_id=instrument_id, provider_code="future-provider", vendor_instrument_id="token", valid_to=date(2024, 12, 31), is_active=True)
    session.scalars.return_value = _Rows([expired])
    with pytest.raises(MarketDataError) as invalid:
        await resolve_mapping(session, instrument_id, "future-provider", date(2025, 1, 1), date(2025, 1, 31))
    assert invalid.value.code == "market_data_mapping_expired"
    first = InstrumentVendorMapping(instrument_id=instrument_id, provider_code="future-provider", vendor_instrument_id="one", is_active=True)
    second = InstrumentVendorMapping(instrument_id=instrument_id, provider_code="future-provider", vendor_instrument_id="two", is_active=True)
    session.scalars.return_value = _Rows([first, second])
    with pytest.raises(MarketDataError, match="ambiguous"):
        await resolve_mapping(session, instrument_id, "future-provider", date(2025, 1, 1), date(2025, 1, 31))


@pytest.mark.asyncio
async def test_provider_timeout_is_bounded_and_sanitized_after_retry():
    class SlowProvider:
        calls = 0
        async def load(self, request):
            import asyncio
            self.calls += 1
            await asyncio.sleep(0.05)
    provider = SlowProvider()
    with pytest.raises(MarketDataError) as raised:
        await load_with_policy(provider, object(), timeout_seconds=0.001, max_retries=1)
    assert raised.value.code == "market_data_timeout"
    assert provider.calls == 2
