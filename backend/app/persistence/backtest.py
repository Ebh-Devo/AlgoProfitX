from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.enums import BacktestStatus


@dataclass(frozen=True, slots=True)
class BacktestRecord:
    id: uuid.UUID
    strategy_id: uuid.UUID
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
    attempt_count: int
    lease_token: str | None
    lease_expires_at: datetime | None
    # Snapshot of the strategy version's definition schema version (1 when not recorded).
    definition_schema_version: int = 1
