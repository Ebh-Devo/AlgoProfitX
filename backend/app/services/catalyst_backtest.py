from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.backtesting.contracts import BacktestExecutionError, BacktestExecutionResult, HistoricalCandleRequest, InstrumentIdentity
from app.backtesting.reference import EmaCrossoverReferenceEngine, SyntheticMarketDataProvider
from app.core.config import get_settings
from app.core.metrics import metrics
from app.core.observability import log_event
from app.market_calendar.contracts import CalendarError
from app.market_calendar.reference import IndianReferenceTradingCalendar
from app.models.instrument import Exchange
from app.persistence.backtest import BacktestRecord
from app.persistence.catalyst.backtest import CatalystBacktestConflict, CatalystBacktestRepository
from app.services.backtest import load_versioned_definition
from app.strategy_definition.runtime.engine import StrategyRuntimeEngine


MAX_RESULT_TRADES = 100
MAX_RESULT_EQUITY_POINTS = 256


def _decimal_string(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.00000001")), "f")


def build_result_summary(result: BacktestExecutionResult) -> dict[str, object]:
    """The ``result_summary`` object persisted for a completed backtest."""
    return {
        "initial_capital": _decimal_string(result.initial_capital),
        "final_equity": _decimal_string(result.final_equity),
        "total_return": _decimal_string(result.total_return),
        "trade_count": len(result.trades),
        "trades": list(result.trades),
        "equity_curve": list(result.equity_curve),
        "engine_identifier": result.engine_identifier,
        "provider_identifier": result.provider_identifier,
    }


def _historical_request(backtest: BacktestRecord) -> HistoricalCandleRequest:
    snapshot = backtest.instrument_snapshot
    if snapshot is None or backtest.instrument_id is None:
        raise BacktestExecutionError("Backtest Instrument is unresolved")
    try:
        identity = InstrumentIdentity(id=str(backtest.instrument_id), **snapshot)
        exchange = Exchange(
            code=identity.exchange_code,
            name=identity.exchange_code,
            country_code="IN",
            timezone=identity.exchange_timezone,
            default_currency=identity.quote_currency,
            calendar_code=f"X{identity.exchange_code}",
            is_active=identity.exchange_is_active,
        )
    except (TypeError, ValueError) as exc:
        raise BacktestExecutionError("Backtest Instrument snapshot is invalid") from exc
    calendar = IndianReferenceTradingCalendar()
    start = backtest.range_start or datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = backtest.range_end or start + timedelta(days=120)
    try:
        sessions = calendar.sessions_between(exchange, start, end)
    except CalendarError as exc:
        raise BacktestExecutionError(str(exc)) from exc
    if not sessions:
        raise BacktestExecutionError("Historical request contains no trading sessions")
    return HistoricalCandleRequest(
        instrument=identity,
        timeframe=backtest.timeframe or "1d",
        start=backtest.range_start,
        end=backtest.range_end,
        adjustment_policy=backtest.adjustment_policy or "unadjusted",
        sessions=sessions,
        metadata={
            "requested_reference": backtest.market_data_reference,
            "calendar": calendar.provenance(exchange, sessions),
        },
    )


async def execute_catalyst_backtest(
    repository: CatalystBacktestRepository,
    backtest_id: uuid.UUID,
) -> BacktestRecord:
    settings = get_settings()
    backtest = await repository.claim(
        backtest_id, lease_seconds=settings.backtest_claim_lease_seconds
    )
    if backtest.lease_token is None:
        raise CatalystBacktestConflict("Backtest lease is unavailable")
    started = time.perf_counter()
    log_event("backtest_started", backtest_id=backtest.id, attempt=backtest.attempt_count)
    metrics.increment("backtest.count", tags={"status": "started"})
    try:
        provider = SyntheticMarketDataProvider()
        if settings.market_data_provider != provider.code:
            raise BacktestExecutionError("Configured market data provider is unavailable")
        # The persisted schema version alone selects the path. A V2 definition is loaded and
        # fully validated before any market data is requested (same contract as the SQL path).
        loaded = load_versioned_definition(backtest)
        request = _historical_request(backtest)
        batch = await provider.load(request)
        if loaded is None:  # V1: the unchanged reference engine
            result = EmaCrossoverReferenceEngine(provider.identifier).run(
                backtest.configuration_snapshot,
                backtest.backtest_configuration_snapshot,
                batch.candles,
            )
        else:  # V2: the strategy runtime over the already-loaded canonical definition
            try:
                result = StrategyRuntimeEngine(
                    provider.identifier, str(backtest.strategy_version_id)
                ).run_canonical(
                    loaded.canonical,
                    backtest.backtest_configuration_snapshot,
                    batch.candles,
                )
            except BacktestExecutionError:
                raise
            except Exception as exc:  # a runtime bug is a terminal strategy failure, not an outage
                log_event("backtest_runtime_failed", level=logging.ERROR, exc_info=True, backtest_id=backtest.id)
                raise BacktestExecutionError("Strategy runtime failed", "strategy_runtime_failed") from exc
        if len(result.trades) > MAX_RESULT_TRADES or len(result.equity_curve) > MAX_RESULT_EQUITY_POINTS:
            raise BacktestExecutionError("Backtest result exceeds its limit")
        summary = build_result_summary(result)
        try:
            completed = await repository.finish_success(
                backtest.id,
                backtest.lease_token,
                result_summary=summary,
                provider=batch.provider_code,
                dataset_reference=batch.dataset_reference,
                fetched_at=batch.fetched_at,
                provenance=batch.provenance,
            )
        except ValueError as exc:
            # The result cannot fit a Data Store text column (10,000 characters). Retrying cannot
            # help, so fail terminally with a clear code instead of cycling through retries.
            raise BacktestExecutionError(
                "Backtest result exceeds the stored size limit", "backtest_result_too_large"
            ) from exc
    except BacktestExecutionError as exc:
        error_code = getattr(exc, "code", None) or "backtest_invalid_request"
        log_event("backtest_failed", level=logging.WARNING, backtest_id=backtest.id, error_code=error_code)
        metrics.increment("backtest.count", tags={"status": "failed", "error_code": error_code})
        return await repository.finish_failure(
            backtest.id, backtest.lease_token, str(exc), error_code
        )
    except Exception:
        log_event("backtest_retry_scheduled", level=logging.ERROR, exc_info=True, backtest_id=backtest.id, attempt=backtest.attempt_count)
        metrics.increment("backtest.count", tags={"status": "retry"})
        return await repository.release_for_retry(
            backtest.id, backtest.lease_token, "backtest_transient_failure"
        )
    duration_ms = (time.perf_counter() - started) * 1000
    log_event("backtest_completed", backtest_id=backtest.id, duration_ms=round(duration_ms, 3))
    metrics.increment("backtest.count", tags={"status": "completed"})
    metrics.observe("backtest.duration_ms", duration_ms, tags={"status": "completed"})
    return completed
