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
    instrument_id: uuid.UUID | None
    instrument_snapshot: dict[str, Any] | None
    requested_by_user_id: uuid.UUID
    status: BacktestStatus
    configuration_snapshot: dict[str, Any]
    backtest_configuration_snapshot: dict[str, Any]
    market_data_reference: str | None
    market_data_provider: str | None
    market_data_dataset_id: uuid.UUID | None
    dataset_reference: str | None
    timeframe: str | None
    range_start: datetime | None
    range_end: datetime | None
    adjustment_policy: str | None
    data_fetched_at: datetime | None
    market_data_provenance: dict[str, Any] | None
    result_summary: dict[str, Any] | None
    error_message: str | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class AnalyticsEquityCurvePoint(BaseModel):
    timestamp: str
    equity: str


class BacktestAnalyticsResponse(BaseModel):
    backtest_id: uuid.UUID
    engine_identifier: str
    provider_identifier: str
    initial_capital: str
    final_equity: str
    total_return: str
    trade_count: int
    win_rate: str | None
    profit_factor: str | None
    average_win: str | None
    average_loss: str | None
    max_drawdown: str
    equity_curve: list[AnalyticsEquityCurvePoint]
