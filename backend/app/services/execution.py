import uuid
from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.allocation import AllocationIntent, AllocationStatus
from app.models.execution import ExecutionIntent, ExecutionStatus
from app.models.strategy import Strategy, StrategyStatus, StrategyVersion
from app.paper_execution.contracts import PaperExecutionError
from app.paper_execution.reference import (
    EmaCrossoverPaperAdapter,
    SyntheticPaperMarketDataProvider,
)


MAX_PAPER_RESULT_BYTES = 8_192
SUPPORTED_PAPER_CURRENCY = "USD"


class ExecutionIntentConflict(Exception):
    pass


class ExecutionIntentEligibilityError(Exception):
    pass


class PaperExecutionConflict(Exception):
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


async def execute_paper_execution_intent(
    session: AsyncSession,
    execution_intent_id: uuid.UUID,
    investor_user_id: uuid.UUID,
) -> ExecutionIntent:
    execution_intent = await _claim_pending_execution_intent(
        session,
        execution_intent_id,
        investor_user_id,
    )

    try:
        allocation, strategy, version = await _revalidate_execution_intent(
            session,
            execution_intent,
        )
        if execution_intent.currency_snapshot != SUPPORTED_PAPER_CURRENCY:
            raise PaperExecutionError(
                "unsupported_currency",
                "Paper execution supports only allocation currency USD",
            )
        provider = SyntheticPaperMarketDataProvider()
        adapter = EmaCrossoverPaperAdapter(provider.identifier)
        candles = provider.load(version.configuration)
        result = adapter.execute(
            version.configuration,
            execution_intent.notional_amount_snapshot,
            candles,
        )
        result_summary = _paper_result_summary(
            execution_intent,
            version.configuration,
            result,
        )
        _validate_result_size(result_summary)
    except PaperExecutionError as exc:
        return await _mark_execution_intent_failed(
            session,
            execution_intent.id,
            exc.error_code,
            str(exc),
        )
    except Exception:
        return await _mark_execution_intent_failed(
            session,
            execution_intent.id,
            "execution_calculation_failure",
            "Paper execution failed",
        )

    return await _mark_execution_intent_completed(
        session,
        execution_intent.id,
        result_summary,
    )


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


async def _claim_pending_execution_intent(
    session: AsyncSession,
    execution_intent_id: uuid.UUID,
    investor_user_id: uuid.UUID,
) -> ExecutionIntent:
    result = await session.execute(
        select(ExecutionIntent)
        .where(
            ExecutionIntent.id == execution_intent_id,
            ExecutionIntent.investor_user_id == investor_user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    execution_intent = result.scalar_one_or_none()
    if execution_intent is None:
        raise LookupError("Execution intent not found")
    if execution_intent.status != ExecutionStatus.PENDING:
        raise PaperExecutionConflict(
            f"Execution intent cannot execute while {execution_intent.status.value}"
        )

    execution_intent.status = ExecutionStatus.RUNNING
    execution_intent.started_at = datetime.now(timezone.utc)
    execution_intent.completed_at = None
    execution_intent.error_code = None
    execution_intent.error_message = None
    execution_intent.paper_result_summary = None
    await session.commit()
    await session.refresh(execution_intent)
    return execution_intent


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


async def _revalidate_execution_intent(
    session: AsyncSession,
    execution_intent: ExecutionIntent,
) -> tuple[AllocationIntent, Strategy, StrategyVersion]:
    if execution_intent.mode != "paper":
        raise PaperExecutionError(
            "invalid_strategy_configuration",
            "Execution intent is not configured for paper mode",
        )
    if execution_intent.notional_amount_snapshot <= Decimal("0"):
        raise PaperExecutionError(
            "execution_calculation_failure",
            "Execution intent notional amount must be positive",
        )

    allocation_result = await session.execute(
        select(AllocationIntent)
        .where(
            AllocationIntent.id == execution_intent.allocation_intent_id,
            AllocationIntent.investor_user_id == execution_intent.investor_user_id,
        )
        .with_for_update()
    )
    allocation = allocation_result.scalar_one_or_none()
    if allocation is None:
        raise PaperExecutionError(
            "allocation_unavailable",
            "Allocation is unavailable for paper execution",
        )
    if allocation.status != AllocationStatus.ACTIVE:
        raise PaperExecutionError(
            "allocation_inactive",
            "Allocation is not active for paper execution",
        )
    if (
        allocation.strategy_id != execution_intent.strategy_id
        or allocation.strategy_version_id != execution_intent.strategy_version_id
    ):
        raise PaperExecutionError(
            "allocation_unavailable",
            "Allocation no longer matches the execution intent",
        )

    strategy_result = await session.execute(
        select(Strategy)
        .where(Strategy.id == execution_intent.strategy_id)
        .with_for_update()
    )
    strategy = strategy_result.scalar_one_or_none()
    if (
        strategy is None
        or strategy.status != StrategyStatus.DEPLOYED
        or not strategy.is_public
    ):
        raise PaperExecutionError(
            "strategy_not_executable",
            "Strategy is not eligible for paper execution",
        )

    version_result = await session.execute(
        select(StrategyVersion).where(
            StrategyVersion.id == execution_intent.strategy_version_id,
            StrategyVersion.strategy_id == execution_intent.strategy_id,
        )
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        raise PaperExecutionError(
            "allocation_unavailable",
            "Execution intent strategy version is unavailable",
        )
    return allocation, strategy, version


async def _mark_execution_intent_completed(
    session: AsyncSession,
    execution_intent_id: uuid.UUID,
    result_summary: dict,
) -> ExecutionIntent:
    execution_intent = await _get_locked_execution_intent(session, execution_intent_id)
    execution_intent.status = ExecutionStatus.COMPLETED
    execution_intent.completed_at = datetime.now(timezone.utc)
    execution_intent.error_code = None
    execution_intent.error_message = None
    execution_intent.paper_result_summary = result_summary
    await session.commit()
    await session.refresh(execution_intent)
    return execution_intent


async def _mark_execution_intent_failed(
    session: AsyncSession,
    execution_intent_id: uuid.UUID,
    error_code: str,
    error_message: str,
) -> ExecutionIntent:
    execution_intent = await _get_locked_execution_intent(session, execution_intent_id)
    execution_intent.status = ExecutionStatus.FAILED
    execution_intent.completed_at = datetime.now(timezone.utc)
    execution_intent.error_code = error_code[:100]
    execution_intent.error_message = _sanitize_error(error_message)
    execution_intent.paper_result_summary = None
    await session.commit()
    await session.refresh(execution_intent)
    return execution_intent


async def _get_locked_execution_intent(
    session: AsyncSession,
    execution_intent_id: uuid.UUID,
) -> ExecutionIntent:
    result = await session.execute(
        select(ExecutionIntent)
        .where(ExecutionIntent.id == execution_intent_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def _paper_result_summary(execution_intent, configuration, result) -> dict:
    return {
        "engine_identifier": result.engine_identifier,
        "provider_identifier": result.provider_identifier,
        "instrument": configuration["instrument"],
        "quote_currency": SUPPORTED_PAPER_CURRENCY,
        "signal": result.signal,
        "notional_amount": _decimal_string(execution_intent.notional_amount_snapshot),
        "order": result.order,
        "fill": result.fill,
        "position": result.position,
    }


def _validate_result_size(result_summary: dict) -> None:
    encoded = json.dumps(result_summary, separators=(",", ":"), sort_keys=True)
    if len(encoded.encode("utf-8")) > MAX_PAPER_RESULT_BYTES:
        raise PaperExecutionError(
            "execution_calculation_failure",
            "Paper execution result exceeds its limit",
        )


def _sanitize_error(error_message: str) -> str:
    normalized = " ".join(error_message.split())
    return (normalized or "Paper execution failed")[:500]


def _decimal_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")
