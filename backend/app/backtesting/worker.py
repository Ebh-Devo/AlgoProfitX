import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.core.config import get_settings
from app.core.observability import log_event
from app.db.session import AsyncSessionLocal
from app.models.backtest import Backtest, BacktestStatus
from app.services.backtest import BacktestExecutionConflict, execute_backtest
from app.persistence.catalyst import CatalystBacktestRepository, CatalystPersistenceClient
from app.services.catalyst_backtest import process_oldest_catalyst_backtest


logger = logging.getLogger(__name__)


async def _recover_stale_backtests() -> int:
    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=settings.backtest_worker_stale_seconds
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(Backtest)
            .where(
                Backtest.status == BacktestStatus.RUNNING,
                Backtest.started_at < cutoff,
            )
            .values(
                status=BacktestStatus.QUEUED,
                started_at=None,
                completed_at=None,
                error_message=None,
                error_code=None,
            )
        )
        await session.commit()
        return result.rowcount


async def _oldest_queued_backtest_id():
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Backtest.id)
            .where(Backtest.status == BacktestStatus.QUEUED)
            .order_by(Backtest.created_at, Backtest.id)
            .limit(1)
        )
        return result.scalar_one_or_none()


async def run_backtest_worker(stop_event: asyncio.Event) -> None:
    settings = get_settings()
    catalyst_repository = (
        CatalystBacktestRepository(CatalystPersistenceClient())
        if settings.uses_catalyst_persistence
        else None
    )
    while not stop_event.is_set():
        try:
            if catalyst_repository is not None:
                processed = await process_oldest_catalyst_backtest(catalyst_repository)
                if processed is None:
                    try:
                        await asyncio.wait_for(
                            stop_event.wait(), timeout=settings.backtest_worker_poll_seconds
                        )
                    except asyncio.TimeoutError:
                        pass
                continue
            recovered = await _recover_stale_backtests()
            if recovered:
                log_event("backtest_stale_jobs_requeued", count=recovered)
            backtest_id = await _oldest_queued_backtest_id()
            if backtest_id is None:
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=settings.backtest_worker_poll_seconds
                    )
                except asyncio.TimeoutError:
                    pass
                continue
            async with AsyncSessionLocal() as session:
                try:
                    await execute_backtest(session, backtest_id)
                except BacktestExecutionConflict:
                    logger.info("Backtest was claimed before worker execution")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Backtest worker iteration failed")
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.backtest_worker_poll_seconds
                )
            except asyncio.TimeoutError:
                pass
