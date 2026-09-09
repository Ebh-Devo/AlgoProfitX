from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.models.strategy import StrategyStatus


@dataclass(frozen=True, slots=True)
class StrategyRecord:
    id: uuid.UUID
    creator_id: uuid.UUID
    name: str
    slug: str
    description: str | None
    status: StrategyStatus
    is_public: bool
    current_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    deployed_at: datetime | None


class DuplicateStrategySlug(ValueError):
    pass


class StrategyRepository(Protocol):
    async def create_strategy(
        self, *, creator_id: uuid.UUID, name: str, slug: str, description: str | None
    ) -> StrategyRecord: ...

    async def list_strategies(self, creator_id: uuid.UUID) -> list[StrategyRecord]: ...

    async def get_strategy(
        self, *, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> StrategyRecord | None: ...

    async def update_strategy(
        self,
        *,
        strategy_id: uuid.UUID,
        creator_id: uuid.UUID,
        updates: dict[str, object],
    ) -> StrategyRecord | None: ...

    async def delete_strategy(
        self, *, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> bool: ...
