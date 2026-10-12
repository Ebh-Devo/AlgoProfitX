from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domain.enums import ExecutionStatus


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
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
