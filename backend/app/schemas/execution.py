import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.models.execution import ExecutionStatus


class ExecutionIntentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str | None = Field(default=None, min_length=1, max_length=255)


class ExecutionIntentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    allocation_intent_id: uuid.UUID
    investor_user_id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID
    strategy_name: str
    strategy_version_number: int
    instrument_id: uuid.UUID | None
    instrument_snapshot: dict[str, Any] | None
    notional_amount_snapshot: Decimal
    currency_snapshot: str
    mode: str
    status: ExecutionStatus
    idempotency_key: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_code: str | None
    error_message: str | None
    paper_result_summary: dict[str, Any] | None

    @field_serializer("notional_amount_snapshot")
    def serialize_notional_amount_snapshot(self, value: Decimal) -> str:
        return format(value.quantize(Decimal("0.00000001")), "f")
