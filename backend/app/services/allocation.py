import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.allocation import AllocationIntent, AllocationStatus
from app.models.strategy import Strategy, StrategyStatus, StrategyVersion
from app.services.strategy import require_execution_supported
from app.schemas.allocation import AllocationCreateRequest, AllocationUpdateRequest


class AllocationEligibilityError(Exception):
    pass


class AllocationConflict(Exception):
    pass


async def create_allocation(
    session: AsyncSession,
    investor_user_id: uuid.UUID,
    data: AllocationCreateRequest,
) -> AllocationIntent:
    strategy = await _get_eligible_strategy(session, data.strategy_id)
    version = await _get_current_strategy_version(session, strategy)
    require_execution_supported(version, "allocate")

    allocation = AllocationIntent(
        investor_user_id=investor_user_id,
        strategy_id=strategy.id,
        strategy_version_id=version.id,
        notional_amount=data.notional_amount,
        currency=data.currency,
        status=AllocationStatus.ACTIVE,
    )
    session.add(allocation)
    await session.flush()
    await session.refresh(allocation)
    return allocation


async def get_allocations_for_investor(
    session: AsyncSession,
    investor_user_id: uuid.UUID,
) -> list[AllocationIntent]:
    result = await session.execute(
        select(AllocationIntent)
        .where(AllocationIntent.investor_user_id == investor_user_id)
        .order_by(AllocationIntent.created_at.desc(), AllocationIntent.id.desc())
    )
    return list(result.scalars().all())


async def get_allocation(
    session: AsyncSession,
    allocation_id: uuid.UUID,
    investor_user_id: uuid.UUID,
) -> AllocationIntent | None:
    result = await session.execute(
        select(AllocationIntent).where(
            AllocationIntent.id == allocation_id,
            AllocationIntent.investor_user_id == investor_user_id,
        )
    )
    return result.scalar_one_or_none()


async def update_allocation(
    session: AsyncSession,
    allocation: AllocationIntent,
    data: AllocationUpdateRequest,
) -> AllocationIntent:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(allocation, field, value)
    await session.flush()
    await session.refresh(allocation)
    return allocation


async def delete_allocation(
    session: AsyncSession,
    allocation: AllocationIntent,
) -> None:
    from app.models.execution import ExecutionIntent

    locked = await session.scalar(
        select(AllocationIntent)
        .where(AllocationIntent.id == allocation.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise AllocationConflict("Allocation not found")

    existing_execution_intent = await session.scalar(
        select(ExecutionIntent.id)
        .where(ExecutionIntent.allocation_intent_id == allocation.id)
        .limit(1)
    )
    if existing_execution_intent is not None:
        raise AllocationConflict(
            "Allocation with execution intents cannot be deleted"
        )
    await session.delete(locked)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise AllocationConflict(
            "Allocation with execution intents cannot be deleted"
        ) from exc


async def _get_eligible_strategy(
    session: AsyncSession,
    strategy_id: uuid.UUID,
) -> Strategy:
    result = await session.execute(
        select(Strategy)
        .where(Strategy.id == strategy_id)
        .with_for_update()
    )
    strategy = result.scalar_one_or_none()
    if (
        strategy is None
        or strategy.status != StrategyStatus.DEPLOYED
        or not strategy.is_public
    ):
        raise AllocationEligibilityError("Strategy is not eligible for allocation")
    return strategy


async def _get_current_strategy_version(
    session: AsyncSession,
    strategy: Strategy,
) -> StrategyVersion:
    if strategy.current_version_id is None:
        raise AllocationEligibilityError(
            "Strategy requires a current version before allocation"
        )

    result = await session.execute(
        select(StrategyVersion).where(
            StrategyVersion.id == strategy.current_version_id,
            StrategyVersion.strategy_id == strategy.id,
        )
    )
    version = result.scalar_one_or_none()
    if version is None:
        raise AllocationEligibilityError(
            "Strategy requires a valid current version before allocation"
        )
    return version
