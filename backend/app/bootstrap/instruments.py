import asyncio
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.instrument import Exchange, Instrument, InstrumentType


BOOTSTRAP_VERSION = "phase-2a-v1"

NSE_EXCHANGE_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
BSE_EXCHANGE_ID = uuid.UUID("10000000-0000-4000-8000-000000000002")
SYNTHETIC_EQUITY_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")
NIFTY_50_INDEX_ID = uuid.UUID("20000000-0000-4000-8000-000000000002")
BANK_NIFTY_INDEX_ID = uuid.UUID("20000000-0000-4000-8000-000000000003")


@dataclass(frozen=True)
class ExchangeSeed:
    id: uuid.UUID
    code: str
    name: str
    country_code: str
    timezone: str
    default_currency: str
    calendar_code: str


@dataclass(frozen=True)
class InstrumentSeed:
    id: uuid.UUID
    exchange_id: uuid.UUID
    canonical_symbol: str
    exchange_symbol: str
    name: str
    instrument_type: InstrumentType
    quote_currency: str
    tick_size: Decimal | None
    lot_size: int | None
    is_tradeable: bool
    is_synthetic: bool = False


EXCHANGES = (
    ExchangeSeed(NSE_EXCHANGE_ID, "NSE", "National Stock Exchange of India", "IN", "Asia/Kolkata", "INR", "XNSE"),
    ExchangeSeed(BSE_EXCHANGE_ID, "BSE", "BSE Limited", "IN", "Asia/Kolkata", "INR", "XBOM"),
)

INSTRUMENTS = (
    InstrumentSeed(
        SYNTHETIC_EQUITY_ID,
        NSE_EXCHANGE_ID,
        "TRADEEBH_TEST_EQ",
        "TRADEEBH_TEST_EQ",
        "TradeEBH Synthetic Reference Equity (not a real security)",
        InstrumentType.EQUITY,
        "INR",
        Decimal("0.01"),
        1,
        True,
        True,
    ),
    InstrumentSeed(
        NIFTY_50_INDEX_ID,
        NSE_EXCHANGE_ID,
        "NSE:NIFTY_50",
        "NIFTY 50",
        "NIFTY 50 Index",
        InstrumentType.INDEX,
        "INR",
        None,
        None,
        False,
    ),
    InstrumentSeed(
        BANK_NIFTY_INDEX_ID,
        NSE_EXCHANGE_ID,
        "NSE:BANK_NIFTY",
        "NIFTY BANK",
        "BANK NIFTY Index",
        InstrumentType.INDEX,
        "INR",
        None,
        None,
        False,
    ),
)


async def bootstrap_market_foundation(session: AsyncSession) -> tuple[int, int]:
    for seed in EXCHANGES:
        exchange = await session.get(Exchange, seed.id)
        if exchange is None:
            exchange = Exchange(id=seed.id)
            session.add(exchange)
        for field, value in seed.__dict__.items():
            setattr(exchange, field, value)
        exchange.is_active = True

    await session.flush()

    for seed in INSTRUMENTS:
        instrument = await session.get(Instrument, seed.id)
        if instrument is None:
            instrument = Instrument(id=seed.id)
            session.add(instrument)
        for field, value in seed.__dict__.items():
            setattr(instrument, field, value)
        instrument.is_active = True
        instrument.isin = None

    await session.commit()
    return len(EXCHANGES), len(INSTRUMENTS)


async def _run() -> None:
    async with AsyncSessionLocal() as session:
        exchanges, instruments = await bootstrap_market_foundation(session)
    print(
        f"Market bootstrap {BOOTSTRAP_VERSION} complete: "
        f"{exchanges} exchanges, {instruments} instruments."
    )


if __name__ == "__main__":
    asyncio.run(_run())
