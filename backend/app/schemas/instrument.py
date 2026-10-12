import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_serializer

from app.domain.enums import InstrumentType


class ExchangeSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    country_code: str
    timezone: str
    default_currency: str
    calendar_code: str
    is_active: bool


class InstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    exchange: ExchangeSummaryResponse
    canonical_symbol: str
    exchange_symbol: str
    name: str
    instrument_type: InstrumentType
    quote_currency: str
    tick_size: Decimal | None
    lot_size: int | None
    is_tradeable: bool
    isin: str | None
    is_synthetic: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("tick_size")
    def serialize_tick_size(self, value: Decimal | None) -> str | None:
        return format(value, "f") if value is not None else None
