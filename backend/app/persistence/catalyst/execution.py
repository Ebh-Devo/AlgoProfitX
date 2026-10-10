from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.models.allocation import AllocationStatus
from app.models.execution import ExecutionStatus
from app.persistence.catalyst.allocation import CatalystAllocationRepository
from app.persistence.catalyst.paging import query_all, select_list
from app.persistence.catalyst.client import CatalystPersistenceClient, CatalystPersistenceError
from app.persistence.catalyst.strategy import CatalystStrategyRepository
from app.persistence.execution import ExecutionRecord
from app.persistence.strategy import StrategyVersionRecord


EXECUTIONS_TABLE = "AlgoProfitXExecutions"
EXECUTION_CLAIMS_TABLE = "AlgoProfitXExecutionClaims"
_SAFE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SAFE_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ROWID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_COLUMNS = (
    "ROWID, execution_uuid, allocation_uuid, investor_uuid, strategy_uuid, "
    "strategy_version_uuid, instrument_uuid, instrument_snapshot, strategy_name, "
    "strategy_version_number, notional_amount, currency, mode, status, "
    "idempotency_key, idempotency_lookup, created_at, "
    "started_at, completed_at, error_code, error_message, paper_result_summary"
)


class CatalystExecutionConflict(ValueError):
    pass


class CatalystExecutionEligibilityError(ValueError):
    pass


def _uuid_literal(value: uuid.UUID) -> str:
    text = str(value)
    if not _SAFE_UUID.fullmatch(text):
        raise ValueError("Invalid Catalyst execution identifier")
    return f"'{text}'"


def _hex_literal(value: str) -> str:
    if not _SAFE_HEX.fullmatch(value):
        raise ValueError("Invalid Catalyst execution lookup")
    return f"'{value}'"


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Execution timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        raise CatalystPersistenceError("Catalyst execution row has invalid time")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalystPersistenceError("Catalyst execution row has invalid time") from exc
    if parsed.tzinfo is None:
        raise CatalystPersistenceError("Catalyst execution row has invalid time")
    return parsed.astimezone(timezone.utc)


def _json(value: dict[str, Any], label: str, limit: int) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > limit:
        raise ValueError(f"{label} exceeds its limit")
    return encoded


def _parse_json(value: Any, label: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst execution row has invalid {label}")
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise CatalystPersistenceError(f"Catalyst execution row has invalid {label}") from exc
    if not isinstance(parsed, dict):
        raise CatalystPersistenceError(f"Catalyst execution row has invalid {label}")
    return parsed


def _row_id(row: dict[str, Any]) -> str:
    value = str(row.get("ROWID", ""))
    if not _SAFE_ROWID.fullmatch(value):
        raise CatalystPersistenceError("Catalyst returned an invalid execution row")
    return value


def _instrument_snapshot(version: StrategyVersionRecord) -> dict[str, Any]:
    instrument = version.instrument
    if instrument is None:
        raise CatalystExecutionEligibilityError("Pinned Strategy Version Instrument is unresolved")
    return {
        "canonical_symbol": instrument.canonical_symbol,
        "exchange_symbol": instrument.exchange_symbol,
        "name": instrument.name,
        "exchange_code": instrument.exchange.code,
        "exchange_timezone": instrument.exchange.timezone,
        "exchange_active": instrument.exchange.is_active,
        "instrument_type": instrument.instrument_type.value,
        "quote_currency": instrument.quote_currency,
        "tick_size": format(instrument.tick_size.normalize(), "f") if instrument.tick_size is not None else None,
        "lot_size": instrument.lot_size,
        "is_tradeable": instrument.is_tradeable,
    }


class CatalystExecutionRepository:
    def __init__(self, client: CatalystPersistenceClient) -> None:
        self._client = client
        self.allocations = CatalystAllocationRepository(client)
        self.strategies = CatalystStrategyRepository(client)

    @staticmethod
    def _record(row: dict[str, Any]) -> ExecutionRecord:
        _row_id(row)
        try:
            record = ExecutionRecord(
                id=uuid.UUID(str(row["execution_uuid"])),
                allocation_intent_id=uuid.UUID(str(row["allocation_uuid"])),
                investor_user_id=uuid.UUID(str(row["investor_uuid"])),
                strategy_id=uuid.UUID(str(row["strategy_uuid"])),
                strategy_version_id=uuid.UUID(str(row["strategy_version_uuid"])),
                instrument_id=uuid.UUID(str(row["instrument_uuid"])) if row.get("instrument_uuid") else None,
                instrument_snapshot=_parse_json(row.get("instrument_snapshot"), "instrument snapshot"),
                strategy_name=str(row["strategy_name"]),
                strategy_version_number=int(row["strategy_version_number"]),
                notional_amount_snapshot=Decimal(str(row["notional_amount"])),
                currency_snapshot=str(row["currency"]),
                mode=str(row["mode"]),
                status=ExecutionStatus(str(row["status"])),
                idempotency_key=str(row["idempotency_key"]) if row.get("idempotency_key") else None,
                created_at=_parse_time(row.get("created_at")),
                started_at=_parse_time(row.get("started_at"), True),
                completed_at=_parse_time(row.get("completed_at"), True),
                error_code=str(row["error_code"]) if row.get("error_code") else None,
                error_message=str(row["error_message"]) if row.get("error_message") else None,
                paper_result_summary=_parse_json(row.get("paper_result_summary"), "paper result"),
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise CatalystPersistenceError("Catalyst returned an invalid execution row") from exc
        if record.mode != "paper" or record.notional_amount_snapshot <= 0:
            raise CatalystPersistenceError("Catalyst returned an invalid execution row")
        return record

    async def _rows(self, condition: str) -> list[dict[str, Any]]:
        # More than 20 explicit columns exceeds ZCQL's documented limit, so these reads use SELECT *.
        query = f"SELECT {select_list(_COLUMNS)} FROM {EXECUTIONS_TABLE} WHERE {condition}"
        if " LIMIT " in f" {condition.upper()} ":
            return await self._client.async_query_rows(query, EXECUTIONS_TABLE)  # bounded lookup
        return await query_all(self._client, query, EXECUTIONS_TABLE)

    async def _claim_for_execution(self, execution_id: uuid.UUID) -> dict[str, Any] | None:
        rows = await self._client.async_query_rows(
            "SELECT ROWID, allocation_uuid, execution_uuid, created_at "
            f"FROM {EXECUTION_CLAIMS_TABLE} "
            f"WHERE execution_uuid = {_uuid_literal(execution_id)} LIMIT 1",
            EXECUTION_CLAIMS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate execution claims")
        _row_id(rows[0])
        return rows[0]

    async def get_owned(self, execution_id: uuid.UUID, investor_id: uuid.UUID) -> ExecutionRecord | None:
        rows = await self._rows(
            f"execution_uuid = {_uuid_literal(execution_id)} AND investor_uuid = {_uuid_literal(investor_id)} LIMIT 1"
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate executions")
        return self._record(rows[0])

    async def _row_owned(self, execution_id: uuid.UUID, investor_id: uuid.UUID) -> dict[str, Any] | None:
        rows = await self._rows(
            f"execution_uuid = {_uuid_literal(execution_id)} AND investor_uuid = {_uuid_literal(investor_id)} LIMIT 1"
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate executions")
        _row_id(rows[0])
        return rows[0]

    async def list_for_investor(self, investor_id: uuid.UUID) -> list[ExecutionRecord]:
        rows = await self._rows(f"investor_uuid = {_uuid_literal(investor_id)}")
        return sorted((self._record(row) for row in rows), key=lambda item: (item.created_at, str(item.id)), reverse=True)

    async def create(self, *, allocation_id: uuid.UUID, investor_id: uuid.UUID, idempotency_key: str | None) -> tuple[ExecutionRecord, bool]:
        lookup = hashlib.sha256(f"{investor_id}:{idempotency_key}".encode()).hexdigest() if idempotency_key else None
        if lookup:
            rows = await self._rows(f"idempotency_lookup = {_hex_literal(lookup)} LIMIT 1")
            if rows:
                existing = self._record(rows[0])
                if existing.allocation_intent_id != allocation_id:
                    raise CatalystExecutionConflict("Idempotency key is already associated with another allocation")
                return existing, False
        allocation = await self.allocations.get_owned(allocation_id, investor_id)
        if allocation is None:
            raise LookupError("Allocation not found")
        if allocation.status is not AllocationStatus.ACTIVE:
            raise CatalystExecutionEligibilityError("Allocation is not active")
        target = await self.strategies.get_execution_target(allocation.strategy_id, allocation.strategy_version_id)
        if target is None:
            raise CatalystExecutionEligibilityError("Strategy is not eligible for execution")
        strategy, version = target
        snapshot = _instrument_snapshot(version)
        now = datetime.now(timezone.utc)
        execution_id = uuid.uuid4()
        try:
            claim = await self._client.async_insert_row(
                EXECUTION_CLAIMS_TABLE,
                {
                    "allocation_uuid": str(allocation.id),
                    "execution_uuid": str(execution_id),
                    "created_at": _timestamp(now),
                },
            )
        except CatalystPersistenceError:
            raise CatalystExecutionConflict(
                "Allocation already has an active execution intent"
            ) from None
        payload: dict[str, Any] = {
            "execution_uuid": str(execution_id),
            "allocation_uuid": str(allocation.id),
            "investor_uuid": str(investor_id),
            "strategy_uuid": str(strategy.id),
            "strategy_version_uuid": str(version.id),
            "instrument_uuid": str(version.instrument_id),
            "instrument_snapshot": _json(snapshot, "instrument snapshot", 4096),
            "strategy_name": allocation.strategy_name,
            "strategy_version_number": allocation.strategy_version_number,
            "notional_amount": format(allocation.notional_amount, "f"),
            "currency": allocation.currency,
            "mode": "paper",
            "status": ExecutionStatus.PENDING.value,
            "created_at": _timestamp(now),
        }
        if idempotency_key:
            payload["idempotency_key"] = idempotency_key
            payload["idempotency_lookup"] = lookup
        try:
            inserted = await self._client.async_insert_row(EXECUTIONS_TABLE, payload)
        except CatalystPersistenceError:
            claim_row_id = str(claim.get("ROWID", ""))
            if _SAFE_ROWID.fullmatch(claim_row_id):
                await self._client.async_delete_row(EXECUTION_CLAIMS_TABLE, claim_row_id)
            if lookup:
                rows = await self._rows(f"idempotency_lookup = {_hex_literal(lookup)} LIMIT 1")
                if rows:
                    existing = self._record(rows[0])
                    if existing.allocation_intent_id == allocation_id:
                        return existing, False
                    raise CatalystExecutionConflict("Idempotency key is already associated with another allocation") from None
            raise CatalystExecutionConflict("Allocation already has an active execution intent") from None
        return self._record({**payload, **inserted}), True

    async def claim(self, execution_id: uuid.UUID, investor_id: uuid.UUID) -> ExecutionRecord:
        row = await self._row_owned(execution_id, investor_id)
        if row is None:
            raise LookupError("Execution intent not found")
        current = self._record(row)
        if current.status is not ExecutionStatus.PENDING:
            raise CatalystExecutionConflict(f"Execution intent cannot execute while {current.status.value}")
        payload = {"ROWID": _row_id(row), "status": ExecutionStatus.RUNNING.value, "started_at": _timestamp(datetime.now(timezone.utc))}
        await self._client.async_update_row(EXECUTIONS_TABLE, payload)
        return self._record({**row, **payload})

    async def finish(self, execution_id: uuid.UUID, investor_id: uuid.UUID, *, result: dict[str, Any] | None = None, error_code: str | None = None, error_message: str | None = None) -> ExecutionRecord:
        row = await self._row_owned(execution_id, investor_id)
        if row is None:
            raise LookupError("Execution intent not found")
        if str(row.get("status")) != ExecutionStatus.RUNNING.value:
            raise CatalystExecutionConflict("Execution intent is not running")
        failed = error_code is not None
        payload: dict[str, Any] = {
            "ROWID": _row_id(row),
            "status": ExecutionStatus.FAILED.value if failed else ExecutionStatus.COMPLETED.value,
            "completed_at": _timestamp(datetime.now(timezone.utc)),
        }
        if failed:
            payload["error_code"] = error_code[:100]
            payload["error_message"] = " ".join((error_message or "Paper execution failed").split())[:500]
        elif result is not None:
            payload["paper_result_summary"] = _json(result, "paper result", 8192)
        await self._client.async_update_row(EXECUTIONS_TABLE, payload)
        claim = await self._claim_for_execution(execution_id)
        if claim is not None:
            await self._client.async_delete_row(
                EXECUTION_CLAIMS_TABLE, _row_id(claim)
            )
        return self._record({**row, **payload})
