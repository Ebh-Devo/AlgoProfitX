import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.models.allocation import AllocationStatus


class AllocationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: uuid.UUID
    notional_amount: Decimal = Field(
        gt=0,
        max_digits=18,
        decimal_places=8,
    )
    currency: str = Field(
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class AllocationUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notional_amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=18,
        decimal_places=8,
    )
    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Z]{3}$",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("notional_amount")
    @classmethod
    def reject_null_notional_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            raise ValueError("notional_amount cannot be null")
        return value

    @field_validator("currency")
    @classmethod
    def reject_null_currency(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("currency cannot be null")
        return value


class AllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    investor_user_id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID
    notional_amount: Decimal
    currency: str
    status: AllocationStatus
    created_at: datetime
    updated_at: datetime

    @field_serializer("notional_amount")
    def serialize_notional_amount(self, value: Decimal) -> str:
        return format(value.quantize(Decimal("0.00000001")), "f")
