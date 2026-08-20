import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.strategy import Strategy
from app.schemas.strategy import (
    StrategyCreateRequest,
    StrategyUpdateRequest,
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