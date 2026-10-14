import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.domain.enums import InstrumentType  # noqa: F401  (re-exported for existing importers)
from app.domain.market_seed import (  # noqa: F401  (re-exported for existing importers)
    BANK_NIFTY_INDEX_ID,
    BOOTSTRAP_VERSION,
    BSE_EXCHANGE_ID,
    EXCHANGES,
    INSTRUMENTS,
    NIFTY_50_INDEX_ID,
    NSE_EXCHANGE_ID,
    ExchangeSeed,
    InstrumentSeed,
)
from app.instrument_identity import SYNTHETIC_EQUITY_ID, SYNTHETIC_EQUITY_SYMBOL  # noqa: F401
from app.models.instrument import Exchange, Instrument


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
