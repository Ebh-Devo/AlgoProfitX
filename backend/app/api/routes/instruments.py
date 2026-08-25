import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.instrument import InstrumentType
from app.schemas.instrument import InstrumentResponse
from app.services.instrument import get_instrument, get_instruments


router = APIRouter(prefix="/instruments", tags=["Instruments"])


@router.get("", response_model=list[InstrumentResponse])
async def list_instruments(
    session: Annotated[AsyncSession, Depends(get_session)],
    exchange: Annotated[str | None, Query(min_length=2, max_length=20)] = None,
    instrument_type: InstrumentType | None = None,
    symbol: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    is_tradeable: bool | None = None,
    is_active: bool = True,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
):
    return await get_instruments(
        session,
        exchange_code=exchange,
        instrument_type=instrument_type,
        symbol=symbol,
        search=search,
        is_tradeable=is_tradeable,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )


@router.get("/{instrument_id}", response_model=InstrumentResponse)
async def get_instrument_detail(
    instrument_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    instrument = await get_instrument(session, instrument_id)
    if instrument is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrument not found",
        )
    return instrument
