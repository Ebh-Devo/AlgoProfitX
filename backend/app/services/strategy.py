import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import Strategy, StrategyVersion
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyUpdateRequest,
    StrategyVersionCreateRequest,
)


async def create_strategy(
    session: AsyncSession,
    creator_id: uuid.UUID,
    data: StrategyCreateRequest,
) -> Strategy:
    strategy = Strategy(
        creator_id=creator_id,
        name=data.name,
        slug=data.slug,
        description=data.description,
        is_public=data.is_public,
    )

    session.add(strategy)

    try:
        await session.flush()
        await session.refresh(strategy)
    except IntegrityError:
        await session.rollback()
        raise ValueError("Strategy slug is already in use")

    return strategy


async def get_strategies_for_creator(
    session: AsyncSession,
    creator_id: uuid.UUID,
) -> list[Strategy]:
    result = await session.execute(
        select(Strategy)
        .where(Strategy.creator_id == creator_id)
        .order_by(Strategy.created_at.desc())
    )

    return list(result.scalars().all())


async def get_strategy(
    session: AsyncSession,
    strategy_id: uuid.UUID,
    creator_id: uuid.UUID,
) -> Strategy | None:
    result = await session.execute(
        select(Strategy).where(
            Strategy.id == strategy_id,
            Strategy.creator_id == creator_id,
        )
    )

    return result.scalar_one_or_none()


async def update_strategy(
    session: AsyncSession,
    strategy: Strategy,
    data: StrategyUpdateRequest,
) -> Strategy:
    updates = data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(strategy, field, value)

    try:
        await session.flush()
        await session.refresh(strategy)
    except IntegrityError:
        await session.rollback()
        raise ValueError("Strategy slug is already in use")

    return strategy


async def delete_strategy(
    session: AsyncSession,
    strategy: Strategy,
) -> None:
    await session.delete(strategy)
    await session.flush()


async def create_strategy_version(
    session: AsyncSession,
    strategy: Strategy,
    data: StrategyVersionCreateRequest,
) -> StrategyVersion:
    # Lock the parent row so normal API requests allocate one version number at
    # a time for a strategy. The database constraint remains the final guard.
    await session.execute(
        select(Strategy)
        .where(Strategy.id == strategy.id)
        .with_for_update()
    )

    result = await session.execute(
        select(func.coalesce(func.max(StrategyVersion.version_number), 0)).where(
            StrategyVersion.strategy_id == strategy.id
        )
    )
    version_number = result.scalar_one() + 1

    version = StrategyVersion(
        strategy_id=strategy.id,
        version_number=version_number,
        configuration=data.configuration,
        backtest_configuration=data.backtest_configuration,
    )
    session.add(version)

    try:
        await session.flush()
        await session.refresh(version)
    except IntegrityError:
        await session.rollback()
        raise ValueError("Strategy version number is already in use")

    return version


async def get_strategy_versions(
    session: AsyncSession,
    strategy_id: uuid.UUID,
) -> list[StrategyVersion]:
    result = await session.execute(
        select(StrategyVersion)
        .where(StrategyVersion.strategy_id == strategy_id)
        .order_by(StrategyVersion.version_number.asc())
    )

    return list(result.scalars().all())


async def get_strategy_version(
    session: AsyncSession,
    strategy_id: uuid.UUID,
    version_id: uuid.UUID,
) -> StrategyVersion | None:
    result = await session.execute(
        select(StrategyVersion).where(
            StrategyVersion.id == version_id,
            StrategyVersion.strategy_id == strategy_id,
        )
    )

    return result.scalar_one_or_none()
