from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.market_calendar.contracts import CalendarError
from app.market_calendar.reference import IndianReferenceTradingCalendar
from app.paper_execution.contracts import PaperExecutionError
from app.paper_execution.reference import EmaCrossoverPaperAdapter, SyntheticPaperMarketDataProvider
from app.persistence.catalyst.execution import CatalystExecutionRepository
from app.persistence.execution import ExecutionRecord


def _reference_session(instrument: dict):
    exchange = SimpleNamespace(
        code=instrument.get("exchange_code"),
        timezone=instrument.get("exchange_timezone"),
        is_active=instrument.get("exchange_active"),
    )
    try:
        sessions = IndianReferenceTradingCalendar().sessions_between(
            exchange,
            datetime(2025, 1, 1, tzinfo=timezone.utc),
            datetime(2025, 1, 2, tzinfo=timezone.utc),
        )
    except CalendarError as exc:
        raise PaperExecutionError("calendar_unavailable", str(exc)) from exc
    if not sessions:
        raise PaperExecutionError("calendar_unavailable", "No reference trading session is available")
    return sessions[0]


def _summary(intent: ExecutionRecord, result) -> dict:
    summary = {
        "engine_identifier": result.engine_identifier,
        "provider_identifier": result.provider_identifier,
        **result.reference_instrument,
        "signal": result.signal,
        "execution_outcome": result.execution_outcome,
        "no_fill_reason": result.no_fill_reason,
        "notional_amount": format(intent.notional_amount_snapshot.quantize(__import__('decimal').Decimal('0.00000001')), 'f'),
        "order": result.order,
        "fill": result.fill,
        "position": result.position,
    }
    summary["exchange"] = summary.get("exchange_code")
    return summary


async def execute_catalyst_paper_intent(repository: CatalystExecutionRepository, execution_id, investor_id) -> ExecutionRecord:
    intent = await repository.claim(execution_id, investor_id)
    try:
        allocation = await repository.allocations.get_owned(intent.allocation_intent_id, investor_id)
        if allocation is None or allocation.status.value != "active":
            raise PaperExecutionError("allocation_unavailable", "Allocation is unavailable for paper execution")
        target = await repository.strategies.get_execution_target(intent.strategy_id, intent.strategy_version_id)
        if target is None:
            raise PaperExecutionError("strategy_not_executable", "Strategy is not eligible for paper execution")
        _, version = target
        instrument = intent.instrument_snapshot
        if instrument is None:
            raise PaperExecutionError("unresolved_legacy_instrument", "Execution Intent Instrument is unresolved")
        provider = SyntheticPaperMarketDataProvider()
        adapter = EmaCrossoverPaperAdapter(provider.identifier)
        adapter.validate_instrument(instrument, intent.currency_snapshot)
        candles = provider.load(version.configuration, instrument, _reference_session(instrument))
        result = adapter.execute(version.configuration, instrument, intent.notional_amount_snapshot, intent.currency_snapshot, candles)
        return await repository.finish(execution_id, investor_id, result=_summary(intent, result))
    except PaperExecutionError as exc:
        return await repository.finish(execution_id, investor_id, error_code=exc.error_code, error_message=str(exc))
    except Exception:
        return await repository.finish(execution_id, investor_id, error_code="execution_calculation_failure", error_message="Paper execution failed")
