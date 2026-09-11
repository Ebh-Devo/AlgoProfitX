from __future__ import annotations

import hashlib
import json
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models.backtest import BacktestStatus
from app.persistence.backtest import BacktestRecord
from app.persistence.catalyst.client import CatalystPersistenceClient, CatalystPersistenceError
from app.persistence.strategy import StrategyVersionRecord
from app.schemas.backtest import BacktestCreateRequest


BACKTESTS_TABLE = "AlgoProfitXBacktests"
BACKTEST_CLAIMS_TABLE = "AlgoProfitXBacktestClaims"
BACKTEST_TERMINALS_TABLE = "AlgoProfitXBacktestTerminals"
BACKTEST_JOB_POOL = "AlgoProfitXBacktests"
BACKTEST_JOB_POOL_ID = "36851000000414985"
BACKTEST_APPSAIL_ID = "36851000000379407"
BACKTEST_JOB_HEADER = "backtest-v1"
MAX_ATTEMPTS = 3
_SAFE_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_SAFE_HEX = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ROWID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_COLUMNS = (
    "ROWID, backtest_uuid, request_key, strategy_uuid, strategy_version_uuid, "
    "instrument_uuid, requested_by_uuid, status, configuration_snapshot, "
    "backtest_configuration_snapshot, instrument_snapshot, market_data_reference, "
    "market_data_provider, dataset_reference, timeframe, range_start, range_end, "
    "adjustment_policy, data_fetched_at, market_data_provenance, result_summary, "
    "error_message, error_code, attempt_count, lease_token, lease_expires_at, "
    "created_at, started_at, completed_at"
)
_TERMINAL_COLUMNS = (
    "ROWID, backtest_uuid, terminal_key, status, result_summary, error_message, "
    "error_code, market_data_provider, dataset_reference, data_fetched_at, "
    "market_data_provenance, completed_at, lease_token"
)


class CatalystBacktestConflict(ValueError):
    pass


def _literal(value: str, pattern: re.Pattern[str], label: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"Invalid Catalyst {label}")
    return f"'{value}'"


def _row_id(row: dict[str, Any]) -> str:
    value = str(row.get("ROWID", ""))
    if not _SAFE_ROWID.fullmatch(value):
        raise CatalystPersistenceError("Catalyst returned an invalid backtest row")
    return value


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Backtest timestamps must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: Any, label: str, *, optional: bool = True) -> datetime | None:
    if value in {None, ""} and optional:
        return None
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst backtest row has invalid {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalystPersistenceError(f"Catalyst backtest row has invalid {label}") from exc
    if parsed.tzinfo is None:
        raise CatalystPersistenceError(f"Catalyst backtest row has invalid {label}")
    return parsed.astimezone(timezone.utc)


def _json(value: dict[str, Any] | None, label: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain JSON values") from exc
    if len(encoded.encode("utf-8")) > 10000:
        raise ValueError(f"{label} is too large")
    return encoded


def _parse_json(value: Any, label: str, *, optional: bool = True) -> dict[str, Any] | None:
    if (value is None or value == "") and optional:
        return None
    if not isinstance(value, str):
        raise CatalystPersistenceError(f"Catalyst backtest row has invalid {label}")
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise CatalystPersistenceError(f"Catalyst backtest row has invalid {label}") from exc
    if not isinstance(parsed, dict):
        raise CatalystPersistenceError(f"Catalyst backtest row has invalid {label}")
    return parsed


def _snapshot(version: StrategyVersionRecord) -> dict[str, Any] | None:
    item = version.instrument
    if item is None:
        return None
    return {
        "canonical_symbol": item.canonical_symbol,
        "exchange_symbol": item.exchange_symbol,
        "name": item.name,
        "exchange_code": item.exchange.code,
        "instrument_type": item.instrument_type.value,
        "quote_currency": item.quote_currency,
        "tick_size": str(item.tick_size) if item.tick_size is not None else None,
        "lot_size": item.lot_size,
        "is_tradeable": item.is_tradeable,
        "exchange_timezone": item.exchange.timezone,
        "exchange_is_active": item.exchange.is_active,
    }


class CatalystBacktestRepository:
    """Durable Catalyst queue using insert-only claims and terminal receipts."""

    def __init__(self, client: CatalystPersistenceClient) -> None:
        self._client = client

    async def submit_job(self, backtest_id: uuid.UUID) -> None:
        await self._client.async_submit_job(
            {
                "job_name": f"backtest_{backtest_id.hex}_{secrets.token_hex(4)}",
                "jobpool_id": BACKTEST_JOB_POOL_ID,
                "target_type": "AppSail",
                "target_id": BACKTEST_APPSAIL_ID,
                "request_method": "POST",
                "url": "/internal/backtests/process",
                "headers": {
                    "content-type": "application/json",
                    "x-algoprofitx-job": BACKTEST_JOB_HEADER,
                },
                "request_body": json.dumps(
                    {"backtest_id": str(backtest_id)}, separators=(",", ":")
                ),
                "job_config": {"number_of_retries": 2, "retry_interval": 300},
            }
        )

    @staticmethod
    def _record(row: dict[str, Any]) -> BacktestRecord:
        _row_id(row)
        try:
            backtest_id = uuid.UUID(str(row["backtest_uuid"]))
            strategy_id = uuid.UUID(str(row["strategy_uuid"]))
            version_id = uuid.UUID(str(row["strategy_version_uuid"]))
            user_id = uuid.UUID(str(row["requested_by_uuid"]))
            instrument_raw = row.get("instrument_uuid")
            instrument_id = uuid.UUID(str(instrument_raw)) if instrument_raw else None
            status = BacktestStatus(str(row["status"]))
            attempts = int(row.get("attempt_count", 0))
        except (KeyError, TypeError, ValueError) as exc:
            raise CatalystPersistenceError("Catalyst returned an invalid backtest row") from exc
        if attempts < 0 or str(row.get("request_key")) != hashlib.sha256(str(backtest_id).encode("ascii")).hexdigest():
            raise CatalystPersistenceError("Catalyst returned an invalid backtest row")
        created = _parse_time(row.get("created_at"), "creation time", optional=False)
        assert created is not None
        return BacktestRecord(
            id=backtest_id,
            strategy_id=strategy_id,
            strategy_version_id=version_id,
            instrument_id=instrument_id,
            instrument_snapshot=_parse_json(row.get("instrument_snapshot"), "instrument snapshot"),
            requested_by_user_id=user_id,
            status=status,
            configuration_snapshot=_parse_json(row.get("configuration_snapshot"), "configuration", optional=False) or {},
            backtest_configuration_snapshot=_parse_json(row.get("backtest_configuration_snapshot"), "backtest configuration", optional=False) or {},
            market_data_reference=str(row["market_data_reference"]) if row.get("market_data_reference") else None,
            market_data_provider=str(row["market_data_provider"]) if row.get("market_data_provider") else None,
            market_data_dataset_id=None,
            dataset_reference=str(row["dataset_reference"]) if row.get("dataset_reference") else None,
            timeframe=str(row["timeframe"]) if row.get("timeframe") else None,
            range_start=_parse_time(row.get("range_start"), "range start"),
            range_end=_parse_time(row.get("range_end"), "range end"),
            adjustment_policy=str(row["adjustment_policy"]) if row.get("adjustment_policy") else None,
            data_fetched_at=_parse_time(row.get("data_fetched_at"), "fetch time"),
            market_data_provenance=_parse_json(row.get("market_data_provenance"), "provenance"),
            result_summary=_parse_json(row.get("result_summary"), "result"),
            error_message=str(row["error_message"]) if row.get("error_message") else None,
            error_code=str(row["error_code"]) if row.get("error_code") else None,
            created_at=created,
            started_at=_parse_time(row.get("started_at"), "start time"),
            completed_at=_parse_time(row.get("completed_at"), "completion time"),
            attempt_count=attempts,
            lease_token=str(row["lease_token"]) if row.get("lease_token") else None,
            lease_expires_at=_parse_time(row.get("lease_expires_at"), "lease expiry"),
        )

    async def _row(self, backtest_id: uuid.UUID) -> dict[str, Any] | None:
        rows = await self._client.async_query_rows(
            f"SELECT {_COLUMNS} FROM {BACKTESTS_TABLE} WHERE backtest_uuid = {_literal(str(backtest_id), _SAFE_UUID, 'backtest ID')} LIMIT 1",
            BACKTESTS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate backtests")
        return rows[0]

    async def create(self, *, version: StrategyVersionRecord, requested_by_user_id: uuid.UUID, data: BacktestCreateRequest) -> BacktestRecord:
        now = datetime.now(timezone.utc)
        backtest_id = uuid.uuid4()
        config = version.backtest_configuration
        def config_time(key: str) -> str | None:
            raw = config.get(key)
            if raw is None:
                return None
            try:
                parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return _timestamp(parsed)
        timeframe = config.get("timeframe")
        adjustment = config.get("adjustment_policy")
        payload: dict[str, Any] = {
            "backtest_uuid": str(backtest_id),
            "request_key": hashlib.sha256(str(backtest_id).encode("ascii")).hexdigest(),
            "strategy_uuid": str(version.strategy_id),
            "strategy_version_uuid": str(version.id),
            "requested_by_uuid": str(requested_by_user_id),
            "status": BacktestStatus.QUEUED.value,
            "configuration_snapshot": _json(version.configuration, "configuration", required=True),
            "backtest_configuration_snapshot": _json(config, "backtest configuration", required=True),
            "timeframe": timeframe.strip() if isinstance(timeframe, str) and 0 < len(timeframe.strip()) <= 50 else "1d",
            "adjustment_policy": adjustment.strip() if isinstance(adjustment, str) and 0 < len(adjustment.strip()) <= 50 else "unadjusted",
            "attempt_count": 0,
            "created_at": _timestamp(now),
        }
        optional = {
            "instrument_uuid": str(version.instrument_id) if version.instrument_id else None,
            "instrument_snapshot": _json(_snapshot(version), "instrument snapshot"),
            "market_data_reference": data.market_data_reference,
            "range_start": config_time("start_date"),
            "range_end": config_time("end_date"),
        }
        payload.update({key: value for key, value in optional.items() if value is not None})
        inserted = await self._client.async_insert_row(BACKTESTS_TABLE, payload)
        return self._record({**payload, **inserted})

    async def get(self, *, strategy_version_id: uuid.UUID, backtest_id: uuid.UUID) -> BacktestRecord | None:
        row = await self._row(backtest_id)
        if row is None or str(row.get("strategy_version_uuid")) != str(strategy_version_id):
            return None
        return await self._reconcile(row)

    async def list(self, *, strategy_version_id: uuid.UUID, limit: int, offset: int) -> list[BacktestRecord]:
        literal = _literal(str(strategy_version_id), _SAFE_UUID, "version ID")
        rows = await self._client.async_query_rows(
            f"SELECT {_COLUMNS} FROM {BACKTESTS_TABLE} WHERE strategy_version_uuid = {literal}",
            BACKTESTS_TABLE,
        )
        records = [await self._reconcile(row) for row in rows]
        records.sort(key=lambda item: (item.created_at, str(item.id)), reverse=True)
        return records[offset:offset + limit]

    async def oldest_queued(self) -> uuid.UUID | None:
        rows = await self._client.async_query_rows(f"SELECT {_COLUMNS} FROM {BACKTESTS_TABLE}", BACKTESTS_TABLE)
        now = datetime.now(timezone.utc)
        eligible = []
        for row in rows:
            item = await self._reconcile(row)
            if item.status is BacktestStatus.QUEUED or (
                item.status is BacktestStatus.RUNNING and item.lease_expires_at is not None and item.lease_expires_at <= now
            ):
                eligible.append(item)
        if not eligible:
            return None
        return min(eligible, key=lambda item: (item.created_at, str(item.id))).id

    async def _claims(self, backtest_id: uuid.UUID) -> list[dict[str, Any]]:
        return await self._client.async_query_rows(
            f"SELECT ROWID, claim_key, lease_token, attempt_number, claimed_at, expires_at FROM {BACKTEST_CLAIMS_TABLE} "
            f"WHERE backtest_uuid = {_literal(str(backtest_id), _SAFE_UUID, 'backtest ID')}",
            BACKTEST_CLAIMS_TABLE,
        )

    async def claim(self, backtest_id: uuid.UUID, *, lease_seconds: float) -> BacktestRecord:
        row = await self._row(backtest_id)
        if row is None:
            raise CatalystBacktestConflict("Backtest not found")
        current = await self._reconcile(row)
        now = datetime.now(timezone.utc)
        if current.status in {BacktestStatus.COMPLETED, BacktestStatus.FAILED}:
            raise CatalystBacktestConflict(f"Backtest cannot execute while {current.status.value}")
        if current.status is BacktestStatus.RUNNING and (current.lease_expires_at is None or current.lease_expires_at > now):
            raise CatalystBacktestConflict("Backtest is already running")
        claims = await self._claims(backtest_id)
        attempt = max((int(item.get("attempt_number", 0)) for item in claims), default=0) + 1
        if attempt > MAX_ATTEMPTS:
            return await self.finish_failure(backtest_id, current.lease_token, "Backtest retry limit reached", "backtest_retry_exhausted")
        claim_key = hashlib.sha256(f"{backtest_id}:{attempt}".encode("ascii")).hexdigest()
        lease_token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        expires = now + timedelta(seconds=max(1.0, lease_seconds))
        try:
            await self._client.async_insert_row(BACKTEST_CLAIMS_TABLE, {
                "claim_key": claim_key, "lease_token": lease_token, "backtest_uuid": str(backtest_id),
                "attempt_number": attempt, "claimed_at": _timestamp(now), "expires_at": _timestamp(expires),
            })
        except CatalystPersistenceError:
            raise CatalystBacktestConflict("Backtest was claimed by another worker") from None
        payload = {"ROWID": _row_id(row), "status": BacktestStatus.RUNNING.value, "attempt_count": attempt,
                   "lease_token": lease_token, "lease_expires_at": _timestamp(expires), "started_at": _timestamp(now),
                   "completed_at": None, "result_summary": None, "error_message": None, "error_code": None}
        updated = await self._client.async_update_row(BACKTESTS_TABLE, payload)
        return self._record({**row, **payload, **updated})

    async def finish_success(self, backtest_id: uuid.UUID, lease_token: str, *, result_summary: dict[str, Any], provider: str, dataset_reference: str, fetched_at: datetime, provenance: dict[str, Any]) -> BacktestRecord:
        return await self._finish(backtest_id, lease_token, status=BacktestStatus.COMPLETED,
                                  result_summary=result_summary, error_message=None, error_code=None,
                                  provider=provider, dataset_reference=dataset_reference, fetched_at=fetched_at, provenance=provenance)

    async def finish_failure(self, backtest_id: uuid.UUID, lease_token: str | None, error_message: str, error_code: str) -> BacktestRecord:
        return await self._finish(backtest_id, lease_token, status=BacktestStatus.FAILED, result_summary=None,
                                  error_message=" ".join(error_message.split())[:500] or "Backtest execution failed",
                                  error_code=error_code[:100], provider=None, dataset_reference=None, fetched_at=None, provenance=None)

    async def release_for_retry(self, backtest_id: uuid.UUID, lease_token: str, error_code: str) -> BacktestRecord:
        row = await self._row(backtest_id)
        if row is None:
            raise CatalystBacktestConflict("Backtest not found")
        current = self._record(row)
        if current.status is not BacktestStatus.RUNNING or current.lease_token != lease_token:
            raise CatalystBacktestConflict("Backtest lease is no longer active")
        if current.attempt_count >= MAX_ATTEMPTS:
            return await self.finish_failure(
                backtest_id, lease_token, "Backtest retry limit reached", "backtest_retry_exhausted"
            )
        payload = {
            "ROWID": _row_id(row),
            "status": BacktestStatus.QUEUED.value,
            "lease_token": None,
            "lease_expires_at": None,
            "started_at": None,
            "completed_at": None,
            "result_summary": None,
            "error_message": None,
            "error_code": error_code[:100],
        }
        updated = await self._client.async_update_row(BACKTESTS_TABLE, payload)
        return self._record({**row, **payload, **updated})

    async def _finish(self, backtest_id: uuid.UUID, lease_token: str | None, *, status: BacktestStatus,
                      result_summary: dict[str, Any] | None, error_message: str | None, error_code: str | None,
                      provider: str | None, dataset_reference: str | None, fetched_at: datetime | None,
                      provenance: dict[str, Any] | None) -> BacktestRecord:
        row = await self._row(backtest_id)
        if row is None:
            raise CatalystBacktestConflict("Backtest not found")
        current = self._record(row)
        if current.status is BacktestStatus.RUNNING and current.lease_token != lease_token:
            raise CatalystBacktestConflict("Backtest lease is no longer active")
        completed = datetime.now(timezone.utc)
        terminal_key = hashlib.sha256(f"terminal:{backtest_id}".encode("ascii")).hexdigest()
        terminal: dict[str, Any] = {"backtest_uuid": str(backtest_id), "terminal_key": terminal_key,
            "status": status.value, "completed_at": _timestamp(completed), "lease_token": lease_token or "none"}
        values = {"result_summary": _json(result_summary, "result"), "error_message": error_message,
                  "error_code": error_code, "market_data_provider": provider, "dataset_reference": dataset_reference,
                  "data_fetched_at": _timestamp(fetched_at) if fetched_at else None,
                  "market_data_provenance": _json(provenance, "provenance")}
        terminal.update({key: value for key, value in values.items() if value is not None})
        try:
            inserted = await self._client.async_insert_row(BACKTEST_TERMINALS_TABLE, terminal)
            terminal.update(inserted)
        except CatalystPersistenceError:
            existing = await self._terminal(backtest_id)
            if existing is None:
                raise
            terminal = existing
        return await self._project_terminal(row, terminal)

    async def _terminal(self, backtest_id: uuid.UUID) -> dict[str, Any] | None:
        rows = await self._client.async_query_rows(
            f"SELECT {_TERMINAL_COLUMNS} FROM {BACKTEST_TERMINALS_TABLE} WHERE backtest_uuid = {_literal(str(backtest_id), _SAFE_UUID, 'backtest ID')} LIMIT 1",
            BACKTEST_TERMINALS_TABLE,
        )
        if not rows:
            return None
        if len(rows) != 1:
            raise CatalystPersistenceError("Catalyst returned duplicate terminal receipts")
        _row_id(rows[0])
        return rows[0]

    async def _reconcile(self, row: dict[str, Any]) -> BacktestRecord:
        terminal = await self._terminal(uuid.UUID(str(row["backtest_uuid"])))
        return await self._project_terminal(row, terminal) if terminal is not None else self._record(row)

    async def _project_terminal(self, row: dict[str, Any], terminal: dict[str, Any]) -> BacktestRecord:
        status = BacktestStatus(str(terminal["status"]))
        payload: dict[str, Any] = {"ROWID": _row_id(row), "status": status.value,
            "completed_at": terminal["completed_at"], "lease_token": None, "lease_expires_at": None,
            "result_summary": terminal.get("result_summary"), "error_message": terminal.get("error_message"),
            "error_code": terminal.get("error_code"), "market_data_provider": terminal.get("market_data_provider"),
            "dataset_reference": terminal.get("dataset_reference"), "data_fetched_at": terminal.get("data_fetched_at"),
            "market_data_provenance": terminal.get("market_data_provenance")}
        updated = await self._client.async_update_row(BACKTESTS_TABLE, payload)
        return self._record({**row, **payload, **updated})

    async def cleanup(self, backtest_id: uuid.UUID) -> None:
        for table, rows in ((BACKTEST_CLAIMS_TABLE, await self._claims(backtest_id)),):
            for row in rows:
                await self._client.async_delete_row(table, _row_id(row))
        terminal = await self._terminal(backtest_id)
        if terminal is not None:
            await self._client.async_delete_row(BACKTEST_TERMINALS_TABLE, _row_id(terminal))
        row = await self._row(backtest_id)
        if row is not None:
            await self._client.async_delete_row(BACKTESTS_TABLE, _row_id(row))
