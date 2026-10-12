from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from app.domain.enums import InstrumentType
from app.domain.enums import StrategyStatus


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


@dataclass(frozen=True, slots=True)
class ExchangeSnapshotRecord:
    id: uuid.UUID
    code: str
    name: str
    country_code: str
    timezone: str
    default_currency: str
    calendar_code: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class InstrumentSnapshotRecord:
    id: uuid.UUID
    exchange: ExchangeSnapshotRecord
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


@dataclass(frozen=True, slots=True)
class StrategyVersionRecord:
    id: uuid.UUID
    strategy_id: uuid.UUID
    instrument_id: uuid.UUID | None
    instrument: InstrumentSnapshotRecord | None
    version_number: int
    configuration: dict[str, Any]
    backtest_configuration: dict[str, Any]
    created_at: datetime
    # Authoritative V1/V2 selector. Rows stored before the column existed read as 1.
    definition_schema_version: int = 1


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

    async def create_version(
        self,
        *,
        strategy_id: uuid.UUID,
        creator_id: uuid.UUID,
        instrument: InstrumentSnapshotRecord,
        configuration: dict[str, Any],
        backtest_configuration: dict[str, Any],
        definition_schema_version: int = 1,
    ) -> StrategyVersionRecord: ...

    async def list_versions(
        self, *, strategy_id: uuid.UUID, creator_id: uuid.UUID
    ) -> list[StrategyVersionRecord]: ...

    async def get_version(
        self,
        *,
        strategy_id: uuid.UUID,
        version_id: uuid.UUID,
        creator_id: uuid.UUID,
    ) -> StrategyVersionRecord | None: ...
