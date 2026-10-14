from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import AllocationStatus
from app.domain.enums import StrategyStatus
from app.persistence.allocation import AllocationRecord
from app.persistence.catalyst.client import (
    CatalystPersistenceClient,
    CatalystPersistenceError,
)
from app.persistence.catalyst.paging import query_all
from app.persistence.catalyst.strategy import CatalystStrategyRepository
from app.domain.execution_support import require_execution_supported


ALLOCATIONS_TABLE = "AlgoProfitXAllocations"
EXECUTIONS_TABLE = "AlgoProfitXExecutions"
_SAFE_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
_SAFE_ROWID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_COLUMNS = (
    "ROWID, allocation_uuid, investor_uuid, strategy_uuid, "
    "strategy_version_uuid, strategy_name, strategy_version_number, "
    "notional_amount, currency, status, created_at, updated_at"
)


class CatalystAllocationConflict(ValueError):
    pass


class CatalystAllocationEligibilityError(ValueError):
    pass


def _literal(value: uuid.UUID) -> str:
    encoded = str(value)
    if not _SAFE_UUID.fullmatch(encoded):
        raise ValueError("Invalid Catalyst allocation identifier")
    return f"'{encoded}'"


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Allocation timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CatalystPersistenceError("Catalyst allocation row has an invalid timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalystPersistenceError(
            "Catalyst allocation row has an invalid timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise CatalystPersistenceError("Catalyst allocation row has an invalid timestamp")
    return parsed.astimezone(timezone.utc)


def _row_id(row: dict[str, Any]) -> str:
    value = str(row.get("ROWID", ""))
    if not _SAFE_ROWID.fullmatch(value):
        raise CatalystPersistenceError("Catalyst returned an invalid allocation row")
    return value


class CatalystAllocationRepository:
    def __init__(self, client: CatalystPersistenceClient) -> None:
        self._client = client
        self._strategies = CatalystStrategyRepository(client)

    @staticmethod
    def _record(row: dict[str, Any]) -> AllocationRecord:
        _row_id(row)
        try:
            amount = Decimal(str(row["notional_amount"]))
            record = AllocationRecord(
                id=uuid.UUID(str(row["allocation_uuid"])),
                investor_user_id=uuid.UUID(str(row["investor_uuid"])),
                strategy_id=uuid.UUID(str(row["strategy_uuid"])),
                strategy_version_id=uuid.UUID(str(row["strategy_version_uuid"])),
                strategy_name=str(row["strategy_name"]),
                strategy_version_number=int(row["strategy_version_number"]),
                notional_amount=amount,
                currency=str(row["currency"]),
                status=AllocationStatus(str(row["status"])),
                created_at=_parse_timestamp(row.get("created_at")),
                updated_at=_parse_timestamp(row.get("updated_at")),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise CatalystPersistenceError(
                "Catalyst returned an invalid allocation row"
            ) from exc
        if (
            record.notional_amount <= 0
            or not re.fullmatch(r"[A-Z]{3}", record.currency)
            or not record.strategy_name
            or record.strategy_version_number < 1
        ):
            raise CatalystPersistenceError("Catalyst returned an invalid allocation row")
        return record

    async def _owned_row(
        self, allocation_id: uuid.UUID, investor_user_id: uuid.UUID
    ) -> dict[str, Any] | None:
        rows = await self._client.async_query_rows(
            f"SELECT {_COLUMNS} FROM {ALLOCATIONS_TABLE} "
            f"WHERE allocation_uuid = {_literal(allocation_id)} "
            f"AND investor_uuid = {_literal(investor_user_id)} LIMIT 1",
            ALLOCATIONS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate allocations")
        _row_id(rows[0])
        return rows[0]

    async def create(
        self,
        *,
        investor_user_id: uuid.UUID,
        strategy_id: uuid.UUID,
        notional_amount: Decimal,
        currency: str,
    ) -> AllocationRecord:
        target = await self._strategies.get_allocation_target(strategy_id)
        if target is None:
            raise CatalystAllocationEligibilityError(
                "Strategy is not eligible for allocation"
            )
        strategy, version = target
        if strategy.status is not StrategyStatus.DEPLOYED or not strategy.is_public:
            raise CatalystAllocationEligibilityError(
                "Strategy is not eligible for allocation"
            )
        if strategy.current_version_id is None:
            raise CatalystAllocationEligibilityError(
                "Strategy requires a current version before allocation"
            )
        # Same rule as the SQL path: only V1 versions can be allocated (V2 is backtest-only).
        require_execution_supported(version, "allocate")
        now = datetime.now(timezone.utc)
        payload = {
            "allocation_uuid": str(uuid.uuid4()),
            "investor_uuid": str(investor_user_id),
            "strategy_uuid": str(strategy.id),
            "strategy_version_uuid": str(version.id),
            "strategy_name": strategy.name,
            "strategy_version_number": version.version_number,
            "notional_amount": format(notional_amount, "f"),
            "currency": currency,
            "status": AllocationStatus.ACTIVE.value,
            "created_at": _timestamp(now),
            "updated_at": _timestamp(now),
        }
        inserted = await self._client.async_insert_row(ALLOCATIONS_TABLE, payload)
        return self._record({**payload, **inserted})

    async def list_for_investor(
        self, investor_user_id: uuid.UUID
    ) -> list[AllocationRecord]:
        rows = await query_all(
            self._client,
            f"SELECT {_COLUMNS} FROM {ALLOCATIONS_TABLE} "
            f"WHERE investor_uuid = {_literal(investor_user_id)}",
            ALLOCATIONS_TABLE,
        )
        return sorted(
            (self._record(row) for row in rows),
            key=lambda item: (item.created_at, str(item.id)),
            reverse=True,
        )

    async def get_owned(
        self, allocation_id: uuid.UUID, investor_user_id: uuid.UUID
    ) -> AllocationRecord | None:
        row = await self._owned_row(allocation_id, investor_user_id)
        return self._record(row) if row is not None else None

    async def update_owned(
        self,
        *,
        allocation_id: uuid.UUID,
        investor_user_id: uuid.UUID,
        updates: dict[str, object],
    ) -> AllocationRecord | None:
        row = await self._owned_row(allocation_id, investor_user_id)
        if row is None:
            return None
        if not updates.keys() <= {"notional_amount", "currency"}:
            raise ValueError("Invalid allocation update")
        payload: dict[str, Any] = {
            "ROWID": _row_id(row),
            "updated_at": _timestamp(datetime.now(timezone.utc)),
        }
        if "notional_amount" in updates:
            amount = updates["notional_amount"]
            if not isinstance(amount, Decimal) or amount <= 0:
                raise ValueError("Invalid allocation amount")
            payload["notional_amount"] = format(amount, "f")
        if "currency" in updates:
            currency = updates["currency"]
            if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError("Invalid allocation currency")
            payload["currency"] = currency
        await self._client.async_update_row(ALLOCATIONS_TABLE, payload)
        return self._record({**row, **payload})

    async def delete_owned(
        self, allocation_id: uuid.UUID, investor_user_id: uuid.UUID
    ) -> bool:
        row = await self._owned_row(allocation_id, investor_user_id)
        if row is None:
            return False
        allocation_literal = _literal(allocation_id)
        executions = await self._client.async_query_rows(
            f"SELECT ROWID FROM {EXECUTIONS_TABLE} "
            f"WHERE allocation_uuid = {allocation_literal} LIMIT 1",
            EXECUTIONS_TABLE,
        )
        if executions:
            raise CatalystAllocationConflict(
                "Allocation with execution intents cannot be deleted"
            )
        await self._client.async_delete_row(ALLOCATIONS_TABLE, _row_id(row))
        return True
