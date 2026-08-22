import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.bootstrap.instruments import (
    BANK_NIFTY_INDEX_ID,
    BSE_EXCHANGE_ID,
    NIFTY_50_INDEX_ID,
    NSE_EXCHANGE_ID,
    SYNTHETIC_EQUITY_ID,
    bootstrap_market_foundation,
)
from app.db.session import AsyncSessionLocal
from app.models.instrument import Exchange, Instrument, InstrumentType, InstrumentVendorMapping
from tests.test_backtest_execution import client


async def bootstrap() -> None:
    async with AsyncSessionLocal() as session:
        await bootstrap_market_foundation(session)


async def add_exchange(session, code: str = "TEST") -> Exchange:
    exchange = Exchange(
        code=code,
        name=f"{code} Exchange",
        country_code="IN",
        timezone="Asia/Kolkata",
        default_currency="INR",
        calendar_code=f"X{code}",
        is_active=True,
    )
    session.add(exchange)
    await session.flush()
    return exchange


def instrument(exchange_id, **overrides) -> Instrument:
    values = {
        "exchange_id": exchange_id,
        "canonical_symbol": f"TEST:{uuid.uuid4().hex}",
        "exchange_symbol": uuid.uuid4().hex[:12].upper(),
        "name": "Test Equity",
        "instrument_type": InstrumentType.EQUITY,
        "quote_currency": "INR",
        "tick_size": Decimal("0.05"),
        "lot_size": 1,
        "is_tradeable": True,
        "is_synthetic": False,
        "is_active": True,
    }
    values.update(overrides)
    return Instrument(**values)


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent_and_uses_stable_exchange_identity():
    async with AsyncSessionLocal() as session:
        assert await bootstrap_market_foundation(session) == (2, 3)
        assert await bootstrap_market_foundation(session) == (2, 3)
        assert await session.scalar(select(func.count()).select_from(Exchange)) == 2
        assert await session.scalar(select(func.count()).select_from(Instrument)) == 3
        nse = await session.get(Exchange, NSE_EXCHANGE_ID)
        bse = await session.get(Exchange, BSE_EXCHANGE_ID)

    assert nse is not None and nse.code == "NSE"
    assert bse is not None and bse.code == "BSE"
    assert nse.timezone == bse.timezone == "Asia/Kolkata"
    assert nse.default_currency == bse.default_currency == "INR"
    assert nse.country_code == bse.country_code == "IN"


@pytest.mark.asyncio
async def test_bootstrap_equity_and_index_semantics_are_explicit():
    await bootstrap()
    async with AsyncSessionLocal() as session:
        equity = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        nifty = await session.get(Instrument, NIFTY_50_INDEX_ID)
        bank_nifty = await session.get(Instrument, BANK_NIFTY_INDEX_ID)

    assert equity is not None
    assert equity.instrument_type == InstrumentType.EQUITY
    assert equity.is_tradeable is True
    assert equity.tick_size == Decimal("0.01000000")
    assert equity.lot_size == 1
    assert equity.is_synthetic is True
    assert "not a real security" in equity.name
    assert nifty is not None and bank_nifty is not None
    assert nifty.instrument_type == bank_nifty.instrument_type == InstrumentType.INDEX
    assert nifty.is_tradeable is bank_nifty.is_tradeable is False
    assert nifty.tick_size is bank_nifty.tick_size is None
    assert nifty.lot_size is bank_nifty.lot_size is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"tick_size": Decimal("0")},
        {"tick_size": Decimal("-0.01")},
        {"lot_size": 0},
        {"lot_size": -1},
        {"tick_size": None, "is_tradeable": True},
        {"lot_size": None, "is_tradeable": True},
    ],
)
async def test_database_rejects_invalid_tick_lot_and_tradeable_metadata(overrides):
    async with AsyncSessionLocal() as session:
        exchange = await add_exchange(session)
        session.add(instrument(exchange.id, **overrides))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_canonical_symbol_is_global_and_exchange_symbol_is_venue_scoped():
    async with AsyncSessionLocal() as session:
        first_exchange = await add_exchange(session, "ONE")
        second_exchange = await add_exchange(session, "TWO")
        session.add(instrument(first_exchange.id, canonical_symbol="GLOBAL:ONE", exchange_symbol="SHARED"))
        session.add(instrument(second_exchange.id, canonical_symbol="GLOBAL:TWO", exchange_symbol="SHARED"))
        await session.commit()

        session.add(instrument(second_exchange.id, canonical_symbol="GLOBAL:ONE", exchange_symbol="OTHER"))
        with pytest.raises(IntegrityError):
            await session.commit()

    async with AsyncSessionLocal() as session:
        first_exchange = await session.scalar(select(Exchange).where(Exchange.code == "ONE"))
        assert first_exchange is not None
        session.add(instrument(first_exchange.id, canonical_symbol="GLOBAL:THREE", exchange_symbol="SHARED"))
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_vendor_mapping_is_isolated_and_instrument_integrity_is_restrictive(client):
    await bootstrap()
    async with AsyncSessionLocal() as session:
        equity = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        assert equity is not None
        mapping = InstrumentVendorMapping(
            instrument_id=equity.id,
            provider_code="test-provider",
            vendor_instrument_id="private-token-123",
            vendor_symbol="TESTEQ",
            is_active=True,
            provider_metadata={"segment": "synthetic"},
        )
        session.add(mapping)
        await session.commit()

        await session.delete(equity)
        with pytest.raises(IntegrityError):
            await session.commit()

    response = await client.get(f"/api/v1/instruments/{SYNTHETIC_EQUITY_ID}")
    assert response.status_code == 200
    assert "vendor_mappings" not in response.json()
    assert "private-token-123" not in response.text


@pytest.mark.asyncio
async def test_exchange_delete_is_restricted_and_deactivation_is_supported(client):
    await bootstrap()
    async with AsyncSessionLocal() as session:
        nse = await session.get(Exchange, NSE_EXCHANGE_ID)
        assert nse is not None
        await session.delete(nse)
        with pytest.raises(IntegrityError):
            await session.commit()

    async with AsyncSessionLocal() as session:
        nse = await session.get(Exchange, NSE_EXCHANGE_ID)
        assert nse is not None
        nse.is_active = False
        await session.commit()
        assert (await session.get(Exchange, NSE_EXCHANGE_ID)).is_active is False

    response = await client.get("/api/v1/instruments")
    assert response.status_code == 200
    assert response.json() == []
    detail = await client.get(f"/api/v1/instruments/{SYNTHETIC_EQUITY_ID}")
    assert detail.status_code == 200


@pytest.mark.asyncio
async def test_anonymous_list_detail_filters_and_pagination(client):
    await bootstrap()
    response = await client.get("/api/v1/instruments")
    assert response.status_code == 200
    assert len(response.json()) == 3
    assert response.json()[0]["exchange"]["code"] == "NSE"
    assert response.json()[0]["exchange"]["timezone"] == "Asia/Kolkata"
    assert response.json()[0]["quote_currency"] == "INR"

    response = await client.get("/api/v1/instruments?exchange=nse&instrument_type=index&is_tradeable=false")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {str(NIFTY_50_INDEX_ID), str(BANK_NIFTY_INDEX_ID)}

    response = await client.get("/api/v1/instruments?search=bank")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [str(BANK_NIFTY_INDEX_ID)]

    response = await client.get("/api/v1/instruments?symbol=TRADEEBH_TEST_EQ")
    assert response.status_code == 200
    assert response.json()[0]["is_synthetic"] is True

    first_page = await client.get("/api/v1/instruments?limit=1&offset=0")
    second_page = await client.get("/api/v1/instruments?limit=1&offset=1")
    assert first_page.status_code == second_page.status_code == 200
    assert first_page.json()[0]["id"] != second_page.json()[0]["id"]

    detail = await client.get(f"/api/v1/instruments/{SYNTHETIC_EQUITY_ID}")
    assert detail.status_code == 200
    assert detail.json()["canonical_symbol"] == "TRADEEBH_TEST_EQ"
    assert "vendor_instrument_id" not in detail.text


@pytest.mark.asyncio
async def test_inactive_instrument_is_hidden_from_default_discovery_but_readable(client):
    await bootstrap()
    async with AsyncSessionLocal() as session:
        instrument_record = await session.get(Instrument, SYNTHETIC_EQUITY_ID)
        assert instrument_record is not None
        instrument_record.is_active = False
        await session.commit()

    response = await client.get("/api/v1/instruments")
    assert response.status_code == 200
    assert str(SYNTHETIC_EQUITY_ID) not in {item["id"] for item in response.json()}
    inactive = await client.get("/api/v1/instruments?is_active=false")
    assert [item["id"] for item in inactive.json()] == [str(SYNTHETIC_EQUITY_ID)]
    detail = await client.get(f"/api/v1/instruments/{SYNTHETIC_EQUITY_ID}")
    assert detail.status_code == 200
    assert detail.json()["is_active"] is False


@pytest.mark.asyncio
async def test_unknown_instrument_returns_not_found(client):
    response = await client.get(f"/api/v1/instruments/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Instrument not found"}
