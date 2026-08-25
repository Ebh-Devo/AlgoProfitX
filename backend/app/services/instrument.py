import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.instrument import Exchange, Instrument, InstrumentType


async def get_instruments(
    session: AsyncSession,
    *,
    exchange_code: str | None,
    instrument_type: InstrumentType | None,
    symbol: str | None,
    search: str | None,
    is_tradeable: bool | None,
    is_active: bool,
    limit: int,
    offset: int,
) -> list[Instrument]:
    statement = (
        select(Instrument)
        .join(Exchange)
        .options(selectinload(Instrument.exchange))
        .where(
            Instrument.is_active.is_(is_active),
            Exchange.is_active.is_(True),
        )
    )
    if exchange_code is not None:
        statement = statement.where(func.upper(Exchange.code) == exchange_code.upper())
    if instrument_type is not None:
        statement = statement.where(Instrument.instrument_type == instrument_type)
    if symbol is not None:
        normalized_symbol = symbol.strip().upper()
        statement = statement.where(
            or_(
                func.upper(Instrument.canonical_symbol) == normalized_symbol,
                func.upper(Instrument.exchange_symbol) == normalized_symbol,
            )
        )
    if search is not None:
        term = search.strip()
        statement = statement.where(
            or_(
                Instrument.canonical_symbol.icontains(term, autoescape=True),
                Instrument.exchange_symbol.icontains(term, autoescape=True),
                Instrument.name.icontains(term, autoescape=True),
            )
        )
    if is_tradeable is not None:
        statement = statement.where(Instrument.is_tradeable.is_(is_tradeable))

    result = await session.execute(
        statement
        .order_by(Exchange.code.asc(), Instrument.exchange_symbol.asc(), Instrument.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_instrument(session: AsyncSession, instrument_id: uuid.UUID) -> Instrument | None:
    result = await session.execute(
        select(Instrument)
        .options(selectinload(Instrument.exchange))
        .where(Instrument.id == instrument_id)
    )
    return result.scalar_one_or_none()
