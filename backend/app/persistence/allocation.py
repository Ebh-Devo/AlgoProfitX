from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.domain.enums import AllocationStatus


@dataclass(frozen=True, slots=True)
class AllocationRecord:
    id: uuid.UUID
    investor_user_id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version_id: uuid.UUID
    strategy_name: str
    strategy_version_number: int
    notional_amount: Decimal
    currency: str
    status: AllocationStatus
    created_at: datetime
    updated_at: datetime


class AllocationRepository(Protocol):
    async def create(
        self,
        *,
        investor_user_id: uuid.UUID,
        strategy_id: uuid.UUID,
        notional_amount: Decimal,
        currency: str,
    ) -> AllocationRecord: ...

    async def list_for_investor(
        self, investor_user_id: uuid.UUID
    ) -> list[AllocationRecord]: ...

    async def get_owned(
        self, allocation_id: uuid.UUID, investor_user_id: uuid.UUID
    ) -> AllocationRecord | None: ...

    async def update_owned(
        self,
        *,
        allocation_id: uuid.UUID,
        investor_user_id: uuid.UUID,
        updates: dict[str, object],
    ) -> AllocationRecord | None: ...

    async def delete_owned(
        self, allocation_id: uuid.UUID, investor_user_id: uuid.UUID
    ) -> bool: ...
