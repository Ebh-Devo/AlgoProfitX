import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bootstrap.instruments import NSE_EXCHANGE_ID, SYNTHETIC_EQUITY_ID
from app.models.instrument import InstrumentType
from app.persistence.catalyst.instrument import CatalystInstrumentRepository


def exchange_row() -> dict[str, object]:
    return {
        "ROWID": "exchange-row-1",
        "exchange_uuid": str(NSE_EXCHANGE_ID),
        "code": "NSE",
        "name": "National Stock Exchange of India",
        "country_code": "IN",
        "timezone": "Asia/Kolkata",
        "default_currency": "INR",
        "calendar_code": "XNSE",
        "is_active": True,
        "created_at": "2026-09-10T00:00:00+00:00",
        "updated_at": "2026-09-10T00:00:00+00:00",
    }


def instrument_row() -> dict[str, object]:
    symbol = "ALGOPROFITX_TEST_EQ"
    return {
        "ROWID": "instrument-row-1",
        "instrument_uuid": str(SYNTHETIC_EQUITY_ID),
        "exchange_uuid": str(NSE_EXCHANGE_ID),
        "canonical_symbol": symbol,
        "canonical_lookup": hashlib.sha256(symbol.casefold().encode()).hexdigest(),
        "exchange_symbol": symbol,
        "exchange_symbol_key": hashlib.sha256(
            f"{NSE_EXCHANGE_ID}:{symbol.casefold()}".encode()
        ).hexdigest(),
        "name": "AlgoProfitX Synthetic Reference Equity (not a real security)",
        "instrument_type": "equity",
        "quote_currency": "INR",
        "tick_size": "0.01",
        "lot_size": 1,
        "is_tradeable": True,
        "isin": None,
        "is_synthetic": True,
        "is_active": True,
        "created_at": "2026-09-10T00:00:00+00:00",
        "updated_at": "2026-09-10T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_detail_joins_safe_exchange_metadata_without_vendor_fields():
    client = SimpleNamespace(async_query_rows=AsyncMock())
    client.async_query_rows.side_effect = [[instrument_row()], [exchange_row()]]
    repository = CatalystInstrumentRepository(client)

    selected = await repository.get_instrument(SYNTHETIC_EQUITY_ID)

    assert selected is not None
    assert selected.exchange.code == "NSE"
    assert selected.instrument_type is InstrumentType.EQUITY
    assert selected.is_tradeable is True
    assert not hasattr(selected, "vendor_mappings")


@pytest.mark.asyncio
async def test_catalog_filters_are_applied_to_validated_records():
    client = SimpleNamespace(async_query_rows=AsyncMock())
    client.async_query_rows.side_effect = [[instrument_row()], [exchange_row()]]
    repository = CatalystInstrumentRepository(client)

    selected = await repository.list_instruments(
        exchange_code="nse",
        instrument_type=InstrumentType.EQUITY,
        symbol=None,
        search="synthetic",
        is_tradeable=True,
        is_active=True,
        limit=20,
        offset=0,
    )

    assert [item.id for item in selected] == [SYNTHETIC_EQUITY_ID]
