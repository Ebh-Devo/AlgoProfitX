import uuid
from copy import deepcopy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backtest import Backtest, BacktestStatus
from app.models.strategy import StrategyVersion
from app.schemas.backtest import BacktestCreateRequest


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
