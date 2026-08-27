import uuid
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.allocation import AllocationIntent, AllocationStatus
from app.models.execution import ExecutionIntent, ExecutionStatus
from app.models.instrument import Exchange, Instrument
from app.market_calendar.contracts import CalendarError, TradingSession
from app.market_calendar.reference import IndianReferenceTradingCalendar
from app.models.strategy import Strategy, StrategyStatus, StrategyVersion
from app.paper_execution.contracts import PaperExecutionError
from app.paper_execution.reference import (
    EmaCrossoverPaperAdapter,
    SyntheticPaperMarketDataProvider,
)
from app.instrument_identity import SYNTHETIC_EQUITY_ID, is_synthetic_equity_symbol


MAX_PAPER_RESULT_BYTES = 8_192


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

    version = await _require_eligible_strategy(session, allocation)
    instrument = await _canonical_instrument_for_version(session, version)
    if instrument is None:
        raise ExecutionIntentEligibilityError(
            "Pinned Strategy Version Instrument is unresolved"
        )
    execution_intent = ExecutionIntent(
        allocation_intent_id=allocation.id,
        investor_user_id=investor_user_id,
        strategy_id=allocation.strategy_id,
        strategy_version_id=allocation.strategy_version_id,
        instrument_id=instrument.id,
        instrument_snapshot=_instrument_snapshot(instrument),
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
        _, _, version = await _revalidate_execution_intent(
            session,
            execution_intent,
        )
        provider = SyntheticPaperMarketDataProvider()
        adapter = EmaCrossoverPaperAdapter(provider.identifier)
        instrument = await _execution_instrument_snapshot(session, execution_intent, version)
        adapter.validate_instrument(instrument, execution_intent.currency_snapshot)
        reference_session = await _paper_reference_session(session, instrument)
        candles = provider.load(version.configuration, instrument, reference_session)
        result = adapter.execute(
            version.configuration,
            instrument,
            execution_intent.notional_amount_snapshot,
            execution_intent.currency_snapshot,
            candles,
        )
        result_summary = _paper_result_summary(
            execution_intent,
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
) -> StrategyVersion:
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
        select(StrategyVersion)
        .where(
            StrategyVersion.id == allocation.strategy_version_id,
            StrategyVersion.strategy_id == allocation.strategy_id,
        )
        .options(joinedload(StrategyVersion.instrument).joinedload(Instrument.exchange))
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        raise ExecutionIntentEligibilityError(
            "Allocation strategy version is not valid"
        )
    return version


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
        ).options(joinedload(StrategyVersion.instrument).joinedload(Instrument.exchange))
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        raise PaperExecutionError(
            "allocation_unavailable",
            "Execution intent strategy version is unavailable",
        )
    return allocation, strategy, version


async def _canonical_instrument_for_version(
    session: AsyncSession, version: StrategyVersion
) -> Instrument | None:
    if version.instrument is not None:
        return version.instrument
    if not is_synthetic_equity_symbol(version.configuration.get("instrument")):
        return None
    result = await session.execute(
        select(Instrument)
        .where(Instrument.id == SYNTHETIC_EQUITY_ID)
        .options(joinedload(Instrument.exchange))
    )
    return result.scalar_one_or_none()


async def _execution_instrument_snapshot(
    session: AsyncSession,
    execution_intent: ExecutionIntent,
    version: StrategyVersion,
) -> dict:
    if execution_intent.instrument_id is not None and execution_intent.instrument_snapshot is not None:
        return {
            "instrument_id": str(execution_intent.instrument_id),
            **deepcopy(execution_intent.instrument_snapshot),
        }
    instrument = await _canonical_instrument_for_version(session, version)
    if instrument is None:
        raise PaperExecutionError(
            "unresolved_legacy_instrument",
            "Legacy Execution Intent Instrument is unresolved",
        )
    return {"instrument_id": str(instrument.id), **_instrument_snapshot(instrument)}


def _instrument_snapshot(instrument: Instrument) -> dict:
    return {
        "canonical_symbol": instrument.canonical_symbol,
        "exchange_symbol": instrument.exchange_symbol,
        "name": instrument.name,
        "exchange_code": instrument.exchange.code,
        "instrument_type": instrument.instrument_type.value,
        "quote_currency": instrument.quote_currency,
        "tick_size": format(instrument.tick_size.normalize(), "f") if instrument.tick_size is not None else None,
        "lot_size": instrument.lot_size,
        "is_tradeable": instrument.is_tradeable,
    }


async def _paper_reference_session(
    session: AsyncSession, instrument: dict
) -> TradingSession:
    result = await session.execute(
        select(Exchange).where(Exchange.code == instrument.get("exchange_code"))
    )
    exchange = result.scalar_one_or_none()
    if exchange is None:
        raise PaperExecutionError(
            "exchange_unavailable", "Instrument Exchange is unavailable"
        )
    calendar = IndianReferenceTradingCalendar()
    try:
        sessions = calendar.sessions_between(
            exchange,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
    except CalendarError as exc:
        raise PaperExecutionError("calendar_unavailable", str(exc)) from exc
    if not sessions:
        raise PaperExecutionError(
            "calendar_unavailable", "No reference trading session is available"
        )
    return sessions[0]


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


def _paper_result_summary(execution_intent, result) -> dict:
    summary = {
        "engine_identifier": result.engine_identifier,
        "provider_identifier": result.provider_identifier,
        **result.reference_instrument,
        "signal": result.signal,
        "execution_outcome": result.execution_outcome,
        "no_fill_reason": result.no_fill_reason,
        "notional_amount": _decimal_string(execution_intent.notional_amount_snapshot),
        "order": result.order,
        "fill": result.fill,
        "position": result.position,
    }
    summary["exchange"] = summary.get("exchange_code")
    return summary


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
