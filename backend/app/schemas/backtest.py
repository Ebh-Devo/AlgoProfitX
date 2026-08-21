import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.backtest import BacktestStatus


class BacktestCreateRequest(BaseModel):
    market_data_reference: str | None = Field(default=None, max_length=500)


class BacktestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_version_id: uuid.UUID
    requested_by_user_id: uuid.UUID
    status: BacktestStatus
    configuration_snapshot: dict[str, Any]
    backtest_configuration_snapshot: dict[str, Any]
    market_data_reference: str | None
    result_summary: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
