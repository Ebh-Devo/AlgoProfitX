"""SQL-only market-data instrument mapping lookup (SQLAlchemy and the ORM model live here, not in ``infrastructure``)."""
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.market_data.infrastructure import MarketDataError
from app.models.instrument import InstrumentVendorMapping


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
