import uuid
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.contracts import (
    BacktestExecutionError,
    HistoricalCandleRequest,
    InstrumentIdentity,
    MarketDataBatch,
)
from app.backtesting.reference import (
    EmaCrossoverReferenceEngine,
    SyntheticMarketDataProvider,
)
from app.models.backtest import Backtest, BacktestStatus
from app.models.instrument import Exchange
from app.models.strategy import StrategyVersion
from app.market_calendar.contracts import CalendarError
from app.market_calendar.reference import IndianReferenceTradingCalendar
from app.schemas.backtest import BacktestCreateRequest
from app.instrument_identity import (
    LEGACY_SYNTHETIC_EQUITY_SYMBOL,
    is_synthetic_equity_symbol,
)


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
    instrument_snapshot = _instrument_snapshot(strategy_version)
    backtest = Backtest(
        strategy_version_id=strategy_version.id,
        instrument_id=strategy_version.instrument_id,
        instrument_snapshot=instrument_snapshot,
        requested_by_user_id=requested_by_user_id,
        status=BacktestStatus.QUEUED,
        configuration_snapshot=deepcopy(strategy_version.configuration),
        backtest_configuration_snapshot=deepcopy(
            strategy_version.backtest_configuration
        ),
        market_data_reference=data.market_data_reference,
        timeframe=_configuration_string(
            strategy_version.backtest_configuration, "timeframe", "1h"
        ),
        range_start=_configuration_datetime(
            strategy_version.backtest_configuration.get("start_date")
        ),
        range_end=_configuration_datetime(
            strategy_version.backtest_configuration.get("end_date")
        ),
        adjustment_policy=_configuration_string(
            strategy_version.backtest_configuration,
            "adjustment_policy",
            "unadjusted",
        ),
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
        batch = provider.load(await _historical_request(session, backtest))
        await _persist_market_data_batch(session, backtest_id, batch)
        result = engine.run(
            backtest.configuration_snapshot,
            backtest.backtest_configuration_snapshot,
            batch.candles,
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


def _instrument_snapshot(strategy_version: StrategyVersion) -> dict | None:
    instrument = strategy_version.instrument
    if instrument is None:
        return None
    return {
        "canonical_symbol": instrument.canonical_symbol,
        "exchange_symbol": instrument.exchange_symbol,
        "name": instrument.name,
        "exchange_code": instrument.exchange.code,
        "instrument_type": instrument.instrument_type.value,
        "quote_currency": instrument.quote_currency,
        "tick_size": format(instrument.tick_size, "f") if instrument.tick_size is not None else None,
        "lot_size": instrument.lot_size,
        "is_tradeable": instrument.is_tradeable,
        "exchange_timezone": instrument.exchange.timezone,
        "exchange_is_active": instrument.exchange.is_active,
    }


def _configuration_string(configuration: dict, key: str, default: str) -> str:
    value = configuration.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 50:
        return default
    return value.strip()


def _configuration_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


async def _historical_request(session: AsyncSession, backtest: Backtest) -> HistoricalCandleRequest:
    snapshot = backtest.instrument_snapshot
    if snapshot is None:
        if not is_synthetic_equity_symbol(backtest.configuration_snapshot.get("instrument")):
            raise BacktestExecutionError("Legacy Backtest Instrument is unresolved")
        identity = InstrumentIdentity(
            id=None,
            canonical_symbol=LEGACY_SYNTHETIC_EQUITY_SYMBOL,
            exchange_symbol=LEGACY_SYNTHETIC_EQUITY_SYMBOL,
            name="Legacy synthetic reference equity",
            exchange_code="NSE",
            instrument_type="equity",
            quote_currency="INR",
            tick_size="0.01",
            lot_size=1,
            is_tradeable=True,
            exchange_timezone="Asia/Kolkata",
            exchange_is_active=True,
        )
    else:
        identity = InstrumentIdentity(id=str(backtest.instrument_id), **snapshot)
    exchange_result = await session.execute(
        select(Exchange).where(Exchange.code == identity.exchange_code)
    )
    exchange = exchange_result.scalar_one_or_none()
    if exchange is None:
        raise BacktestExecutionError("Historical request Exchange is unavailable")
    calendar = IndianReferenceTradingCalendar()
    start = backtest.range_start or datetime(2025, 1, 1, tzinfo=timezone.utc)
    end = backtest.range_end or start + timedelta(days=30)
    try:
        sessions = calendar.sessions_between(exchange, start, end)
    except CalendarError as exc:
        raise BacktestExecutionError(str(exc)) from exc
    if not sessions:
        raise BacktestExecutionError("Historical request contains no trading sessions")
    return HistoricalCandleRequest(
        instrument=identity,
        timeframe=backtest.timeframe or "1h",
        start=backtest.range_start,
        end=backtest.range_end,
        adjustment_policy=backtest.adjustment_policy or "unadjusted",
        sessions=sessions,
        metadata={
            "requested_reference": backtest.market_data_reference,
            "calendar": calendar.provenance(exchange, sessions),
        },
    )


async def _persist_market_data_batch(
    session: AsyncSession,
    backtest_id: uuid.UUID,
    batch: MarketDataBatch,
) -> None:
    _require_utc(batch.fetched_at, "Market data fetched timestamp")
    _require_utc(batch.actual_range_start, "Market data range start")
    _require_utc(batch.actual_range_end, "Market data range end")
    if batch.actual_range_end < batch.actual_range_start:
        raise BacktestExecutionError("Market data range end precedes start")
    if not batch.provider_code or len(batch.provider_code) > 100:
        raise BacktestExecutionError("Market data provider code is invalid")
    if not batch.dataset_reference or len(batch.dataset_reference) > 500:
        raise BacktestExecutionError("Market data dataset reference is invalid")
    if not batch.timeframe or len(batch.timeframe) > 50:
        raise BacktestExecutionError("Market data timeframe is invalid")
    if not batch.adjustment_policy or len(batch.adjustment_policy) > 50:
        raise BacktestExecutionError("Market data adjustment policy is invalid")
    if not isinstance(batch.provenance, dict):
        raise BacktestExecutionError("Market data provenance must be an object")
    if len(json.dumps(batch.provenance, separators=(",", ":")).encode()) > 8192:
        raise BacktestExecutionError("Market data provenance exceeds its limit")

    backtest = await _get_locked_backtest(session, backtest_id)
    backtest.market_data_provider = batch.provider_code
    backtest.dataset_reference = batch.dataset_reference
    backtest.timeframe = batch.timeframe
    backtest.range_start = batch.actual_range_start
    backtest.range_end = batch.actual_range_end
    backtest.adjustment_policy = batch.adjustment_policy
    backtest.data_fetched_at = batch.fetched_at
    backtest.market_data_provenance = deepcopy(batch.provenance)
    await session.commit()


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise BacktestExecutionError(f"{label} must be UTC-aware")
