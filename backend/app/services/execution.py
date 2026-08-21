import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.allocation import AllocationIntent, AllocationStatus
from app.models.execution import ExecutionIntent, ExecutionStatus
from app.models.strategy import Strategy, StrategyStatus, StrategyVersion


class ExecutionIntentConflict(Exception):
    pass


class ExecutionIntentEligibilityError(Exception):
    pass


async def create_execution_intent(
    session: AsyncSession,
    allocation_id: uuid.UUID,
    investor_user_id: uuid.UUID,
    idempotency_key: str | None,
) -> tuple[ExecutionIntent, bool]:
    if idempotency_key is not None:
        existing = await _get_by_idempotency_key(
            session,
            investor_user_id,
            idempotency_key,
        )
        if existing is not None:
            if existing.allocation_intent_id != allocation_id:
                raise ExecutionIntentConflict(
                    "Idempotency key is already associated with another allocation"
                )
            return existing, False

    allocation = await _get_owned_allocation_for_update(
        session,
        allocation_id,
        investor_user_id,
    )
    if allocation is None:
        raise LookupError("Allocation not found")
    if allocation.status != AllocationStatus.ACTIVE:
        raise ExecutionIntentEligibilityError("Allocation is not active")

    await _require_eligible_strategy(session, allocation)
    execution_intent = ExecutionIntent(
        allocation_intent_id=allocation.id,
        investor_user_id=investor_user_id,
        strategy_id=allocation.strategy_id,
        strategy_version_id=allocation.strategy_version_id,
        notional_amount_snapshot=allocation.notional_amount,
        currency_snapshot=allocation.currency,
        mode="paper",
        status=ExecutionStatus.PENDING,
        idempotency_key=idempotency_key,
    )
    session.add(execution_intent)
    try:
        await session.flush()
        await session.refresh(execution_intent)
    except IntegrityError:
        await session.rollback()
        if idempotency_key is not None:
            existing = await _get_by_idempotency_key(
                session,
                investor_user_id,
                idempotency_key,
            )
            if existing is not None:
                if existing.allocation_intent_id == allocation_id:
                    return existing, False
                raise ExecutionIntentConflict(
                    "Idempotency key is already associated with another allocation"
                )
        raise ExecutionIntentConflict(
            "Allocation already has an active execution intent"
        )
    return execution_intent, True


async def get_execution_intents_for_investor(
    session: AsyncSession,
    investor_user_id: uuid.UUID,
) -> list[ExecutionIntent]:
    result = await session.execute(
        select(ExecutionIntent)
        .where(ExecutionIntent.investor_user_id == investor_user_id)
        .order_by(ExecutionIntent.created_at.desc(), ExecutionIntent.id.desc())
    )
    return list(result.scalars().all())


async def get_execution_intent(
    session: AsyncSession,
    execution_intent_id: uuid.UUID,
    investor_user_id: uuid.UUID,
) -> ExecutionIntent | None:
    result = await session.execute(
        select(ExecutionIntent).where(
            ExecutionIntent.id == execution_intent_id,
            ExecutionIntent.investor_user_id == investor_user_id,
        )
    )
    return result.scalar_one_or_none()


async def _get_owned_allocation_for_update(
    session: AsyncSession,
    allocation_id: uuid.UUID,
    investor_user_id: uuid.UUID,
) -> AllocationIntent | None:
    result = await session.execute(
        select(AllocationIntent)
        .where(
            AllocationIntent.id == allocation_id,
            AllocationIntent.investor_user_id == investor_user_id,
        )
        .with_for_update()
    )
    return result.scalar_one_or_none()


async def _get_by_idempotency_key(
    session: AsyncSession,
    investor_user_id: uuid.UUID,
    idempotency_key: str,
) -> ExecutionIntent | None:
    result = await session.execute(
        select(ExecutionIntent).where(
            ExecutionIntent.investor_user_id == investor_user_id,
            ExecutionIntent.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def _require_eligible_strategy(
    session: AsyncSession,
    allocation: AllocationIntent,
) -> None:
    strategy_result = await session.execute(
        select(Strategy).where(Strategy.id == allocation.strategy_id).with_for_update()
    )
    strategy = strategy_result.scalar_one_or_none()
    if (
        strategy is None
        or strategy.status != StrategyStatus.DEPLOYED
        or not strategy.is_public
    ):
        raise ExecutionIntentEligibilityError(
            "Strategy is not eligible for execution"
        )

    version_result = await session.execute(
        select(StrategyVersion).where(
            StrategyVersion.id == allocation.strategy_version_id,
            StrategyVersion.strategy_id == allocation.strategy_id,
        )
    )
    if version_result.scalar_one_or_none() is None:
        raise ExecutionIntentEligibilityError(
            "Allocation strategy version is not valid"
        )
