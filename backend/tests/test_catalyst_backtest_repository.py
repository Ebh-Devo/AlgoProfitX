import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.backtest import BacktestStatus
from app.models.instrument import InstrumentType
from app.instrument_identity import SYNTHETIC_EQUITY_SYMBOL
from app.persistence.catalyst.backtest import (
    BACKTESTS_TABLE,
    BACKTEST_CLAIMS_TABLE,
    BACKTEST_TERMINALS_TABLE,
    CatalystBacktestConflict,
    CatalystBacktestRepository,
)
from app.persistence.catalyst.client import CatalystPersistenceError
from app.persistence.strategy import ExchangeSnapshotRecord, InstrumentSnapshotRecord, StrategyVersionRecord
from app.schemas.backtest import BacktestCreateRequest
from app.services.catalyst_backtest import execute_catalyst_backtest


class MemoryClient:
    def __init__(self):
        self.rows = {BACKTESTS_TABLE: [], BACKTEST_CLAIMS_TABLE: [], BACKTEST_TERMINALS_TABLE: []}
        self.counter = 0
        self.jobs = []

    async def async_submit_job(self, payload):
        self.jobs.append(payload)
        return {"job_id": str(len(self.jobs))}

    async def async_insert_row(self, table, payload):
        unique = {
            BACKTESTS_TABLE: ("backtest_uuid", "request_key"),
            BACKTEST_CLAIMS_TABLE: ("claim_key", "lease_token"),
            BACKTEST_TERMINALS_TABLE: ("backtest_uuid", "terminal_key"),
        }[table]
        if any(any(row.get(key) == payload.get(key) for key in unique) for row in self.rows[table]):
            raise CatalystPersistenceError("duplicate")
        self.counter += 1
        row = {**payload, "ROWID": str(self.counter)}
        self.rows[table].append(row)
        return row

    async def async_update_row(self, table, payload):
        row = next(item for item in self.rows[table] if item["ROWID"] == payload["ROWID"])
        row.update(payload)
        return dict(row)

    async def async_delete_row(self, table, row_id):
        self.rows[table] = [row for row in self.rows[table] if row["ROWID"] != row_id]

    async def async_query_rows(self, query, table):
        rows = list(self.rows[table])
        for column in ("backtest_uuid", "strategy_version_uuid"):
            match = re.search(rf"{column} = '([^']+)'", query)
            if match:
                rows = [row for row in rows if row.get(column) == match.group(1)]
        if "LIMIT 1" in query:
            rows = rows[:1]
        return [dict(row) for row in rows]


def version() -> StrategyVersionRecord:
    moment = datetime(2026, 9, 10, tzinfo=timezone.utc)
    exchange = ExchangeSnapshotRecord(
        id=uuid.uuid4(), code="NSE", name="NSE", country_code="IN",
        timezone="Asia/Kolkata", default_currency="INR", calendar_code="XNSE", is_active=True,
    )
    instrument = InstrumentSnapshotRecord(
        id=uuid.uuid4(), exchange=exchange, canonical_symbol=SYNTHETIC_EQUITY_SYMBOL,
        exchange_symbol=SYNTHETIC_EQUITY_SYMBOL, name="Synthetic", instrument_type=InstrumentType.EQUITY,
        quote_currency="INR", tick_size=Decimal("0.01"), lot_size=1, is_tradeable=True,
        isin=None, is_synthetic=True, is_active=True, created_at=moment, updated_at=moment,
    )
    return StrategyVersionRecord(
        id=uuid.uuid4(), strategy_id=uuid.uuid4(), instrument_id=instrument.id, instrument=instrument,
        version_number=1,
        configuration={"instrument": SYNTHETIC_EQUITY_SYMBOL, "entry": {"type": "ema_crossover", "fast_period": 5, "slow_period": 20}},
        backtest_configuration={"initial_capital": "100000", "timeframe": "1d"}, created_at=moment,
    )


@pytest.mark.asyncio
async def test_queue_claim_terminal_and_reconciliation_are_durable():
    client = MemoryClient()
    repository = CatalystBacktestRepository(client)
    item = await repository.create(
        version=version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    assert item.status is BacktestStatus.QUEUED
    claimed = await repository.claim(item.id, lease_seconds=30)
    assert claimed.status is BacktestStatus.RUNNING
    assert claimed.attempt_count == 1
    with pytest.raises(CatalystBacktestConflict, match="already running"):
        await repository.claim(item.id, lease_seconds=30)

    completed = await repository.finish_success(
        item.id, claimed.lease_token, result_summary={"trade_count": 0},
        provider="synthetic-local-v1", dataset_reference="synthetic-reference-candles-v1",
        fetched_at=datetime.now(timezone.utc), provenance={"synthetic": True},
    )
    assert completed.status is BacktestStatus.COMPLETED
    assert completed.result_summary == {"trade_count": 0}
    assert len(client.rows[BACKTEST_TERMINALS_TABLE]) == 1

    # A projection write can be repaired from the immutable terminal receipt.
    client.rows[BACKTESTS_TABLE][0].update(status="running", result_summary=None, completed_at=None)
    repaired = await repository.get(strategy_version_id=item.strategy_version_id, backtest_id=item.id)
    assert repaired is not None and repaired.status is BacktestStatus.COMPLETED
    assert repaired.result_summary == {"trade_count": 0}


@pytest.mark.asyncio
async def test_expired_lease_gets_new_insert_only_attempt_and_retries_are_bounded():
    client = MemoryClient()
    repository = CatalystBacktestRepository(client)
    item = await repository.create(
        version=version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    first = await repository.claim(item.id, lease_seconds=1)
    client.rows[BACKTESTS_TABLE][0]["lease_expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    second = await repository.claim(item.id, lease_seconds=30)
    assert second.attempt_count == 2
    assert second.lease_token != first.lease_token
    with pytest.raises(CatalystBacktestConflict, match="no longer active"):
        await repository.finish_failure(item.id, first.lease_token, "late", "late_worker")

    queued = await repository.release_for_retry(item.id, second.lease_token, "transient")
    assert queued.status is BacktestStatus.QUEUED
    third = await repository.claim(item.id, lease_seconds=30)
    exhausted = await repository.release_for_retry(item.id, third.lease_token, "transient")
    assert exhausted.status is BacktestStatus.FAILED
    assert exhausted.error_code == "backtest_retry_exhausted"
    assert len(client.rows[BACKTEST_CLAIMS_TABLE]) == 3


@pytest.mark.asyncio
async def test_reference_execution_completes_from_catalyst_snapshots():
    client = MemoryClient()
    repository = CatalystBacktestRepository(client)
    item = await repository.create(
        version=version(), requested_by_user_id=uuid.uuid4(), data=BacktestCreateRequest()
    )
    completed = await execute_catalyst_backtest(repository, item.id)
    assert completed.status is BacktestStatus.COMPLETED
    assert completed.market_data_provider == "synthetic-local-v1"
    assert completed.dataset_reference == "synthetic-reference-candles-v1"
    assert completed.result_summary is not None
    assert completed.result_summary["engine_identifier"] == "ema-crossover-reference-v1"
    assert len(completed.result_summary["equity_curve"]) == 64


@pytest.mark.asyncio
async def test_submit_job_targets_the_catalyst_appsail_worker_without_secrets():
    client = MemoryClient()
    repository = CatalystBacktestRepository(client)
    backtest_id = uuid.uuid4()
    await repository.submit_job(backtest_id)

    assert len(client.jobs) == 1
    job = client.jobs[0]
    assert job["jobpool_name"] == "AlgoProfitXBacktests"
    assert job["target_type"] == "AppSail"
    assert job["target_name"] == "algoprofitx-api"
    assert job["url"] == "/internal/backtests/process"
    assert str(backtest_id) in job["request_body"]
    assert job["job_config"] == {"number_of_retries": 2, "retry_interval": 300}
