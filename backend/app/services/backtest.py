import uuid
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.contracts import BacktestExecutionError
from app.backtesting.reference import (
    EmaCrossoverReferenceEngine,
    SyntheticMarketDataProvider,
)
from app.models.backtest import Backtest, BacktestStatus
from app.models.strategy import StrategyVersion
from app.schemas.backtest import BacktestCreateRequest


MAX_RESULT_TRADES = 100
MAX_RESULT_EQUITY_POINTS = 256


class BacktestExecutionConflict(Exception):
    pass


async def create_backtest(
    session: AsyncSession,
    strategy_version: StrategyVersion,
    requested_by_user_id: uuid.UUID,
    data: BacktestCreateRequest,
) -> Backtest:
    backtest = Backtest(
        strategy_version_id=strategy_version.id,
        requested_by_user_id=requested_by_user_id,
        status=BacktestStatus.QUEUED,
        configuration_snapshot=deepcopy(strategy_version.configuration),
        backtest_configuration_snapshot=deepcopy(
            strategy_version.backtest_configuration
        ),
        market_data_reference=data.market_data_reference,
    )
    session.add(backtest)
    await session.flush()
    await session.refresh(backtest)
    return backtest


async def get_backtests_for_strategy_version(
    session: AsyncSession,
    strategy_version_id: uuid.UUID,
    limit: int,
    offset: int,
) -> list[Backtest]:
    result = await session.execute(
        select(Backtest)
        .where(Backtest.strategy_version_id == strategy_version_id)
        .order_by(Backtest.created_at.desc(), Backtest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def get_backtest(
    session: AsyncSession,
    strategy_version_id: uuid.UUID,
    backtest_id: uuid.UUID,
) -> Backtest | None:
    result = await session.execute(
        select(Backtest).where(
            Backtest.id == backtest_id,
            Backtest.strategy_version_id == strategy_version_id,
        )
    )
    return result.scalar_one_or_none()


async def execute_backtest(
    session: AsyncSession,
    backtest_id: uuid.UUID,
) -> Backtest:
    backtest = await _claim_queued_backtest(session, backtest_id)
    provider = SyntheticMarketDataProvider()
    engine = EmaCrossoverReferenceEngine(provider.identifier)

    try:
        candles = provider.load(
            backtest.configuration_snapshot,
            backtest.backtest_configuration_snapshot,
            backtest.market_data_reference,
        )
        result = engine.run(
            backtest.configuration_snapshot,
            backtest.backtest_configuration_snapshot,
            candles,
        )
        if len(result.trades) > MAX_RESULT_TRADES:
            raise BacktestExecutionError("Backtest trade result exceeds its limit")
        if len(result.equity_curve) > MAX_RESULT_EQUITY_POINTS:
            raise BacktestExecutionError("Backtest equity result exceeds its limit")
    except BacktestExecutionError as exc:
        return await _mark_backtest_failed(session, backtest_id, str(exc))
    except Exception:
        return await _mark_backtest_failed(
            session,
            backtest_id,
            "Backtest execution failed",
        )

    return await _mark_backtest_completed(
        session,
        backtest_id,
        {
            "initial_capital": _decimal_string(result.initial_capital),
            "final_equity": _decimal_string(result.final_equity),
            "total_return": _decimal_string(result.total_return),
            "trade_count": len(result.trades),
            "trades": list(result.trades),
            "equity_curve": list(result.equity_curve),
            "engine_identifier": result.engine_identifier,
            "provider_identifier": result.provider_identifier,
        },
    )


async def _claim_queued_backtest(
    session: AsyncSession,
    backtest_id: uuid.UUID,
) -> Backtest:
    result = await session.execute(
        select(Backtest)
        .where(Backtest.id == backtest_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    backtest = result.scalar_one()
    if backtest.status != BacktestStatus.QUEUED:
        raise BacktestExecutionConflict(
            f"Backtest cannot execute while {backtest.status.value}"
        )

    backtest.status = BacktestStatus.RUNNING
    backtest.started_at = datetime.now(timezone.utc)
    backtest.completed_at = None
    backtest.result_summary = None
    backtest.error_message = None
    await session.commit()
    await session.refresh(backtest)
    return backtest


async def _mark_backtest_completed(
    session: AsyncSession,
    backtest_id: uuid.UUID,
    result_summary: dict,
) -> Backtest:
    backtest = await _get_locked_backtest(session, backtest_id)
    backtest.status = BacktestStatus.COMPLETED
    backtest.completed_at = datetime.now(timezone.utc)
    backtest.result_summary = result_summary
    backtest.error_message = None
    await session.commit()
    await session.refresh(backtest)
    return backtest


async def _mark_backtest_failed(
    session: AsyncSession,
    backtest_id: uuid.UUID,
    error_message: str,
) -> Backtest:
    backtest = await _get_locked_backtest(session, backtest_id)
    backtest.status = BacktestStatus.FAILED
    backtest.completed_at = datetime.now(timezone.utc)
    backtest.result_summary = None
    backtest.error_message = _sanitize_error(error_message)
    await session.commit()
    await session.refresh(backtest)
    return backtest


async def _get_locked_backtest(
    session: AsyncSession,
    backtest_id: uuid.UUID,
) -> Backtest:
    result = await session.execute(
        select(Backtest)
        .where(Backtest.id == backtest_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def _sanitize_error(error_message: str) -> str:
    normalized = " ".join(error_message.split())
    return (normalized or "Backtest execution failed")[:500]


def _decimal_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")
