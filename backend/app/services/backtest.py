import uuid
import json
import logging
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.contracts import (
    BacktestExecutionError,
    Candle,
    HistoricalCandleRequest,
    InstrumentIdentity,
    MarketDataBatch,
)
from app.backtesting.reference import (
    EmaCrossoverReferenceEngine,
    SyntheticMarketDataProvider,
)
from app.core.config import get_settings
from app.core.metrics import metrics
from app.core.observability import log_event
from app.market_data.infrastructure import MarketDataError, ProviderRegistry, canonical_checksum, dataset_key, load_with_policy, validate_and_normalize
from app.market_data.sql_mapping import resolve_mapping
from app.models.backtest import Backtest, BacktestStatus
from app.models.market_data import MarketDataCandle, MarketDataDataset, MarketDataDatasetStatus
from app.models.instrument import Exchange
from app.models.strategy import StrategyVersion
from app.market_calendar.contracts import CalendarError
from app.market_calendar.reference import IndianReferenceTradingCalendar
from app.schemas.backtest import BacktestCreateRequest
from app.strategy_definition.runtime.engine import StrategyRuntimeEngine
from app.services.backtest_definition import load_versioned_definition
from app.strategy_definition.versioning import LEGACY_SCHEMA_VERSION
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
        definition_schema_version=_snapshot_schema_version(strategy_version),
        configuration_snapshot=deepcopy(strategy_version.configuration),
        backtest_configuration_snapshot=deepcopy(
            strategy_version.backtest_configuration
        ),
        market_data_reference=data.market_data_reference,
        timeframe=_configuration_string(
            strategy_version.backtest_configuration, "timeframe", "1d"
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
    started = time.perf_counter()
    log_event("backtest_started", backtest_id=backtest.id)
    metrics.increment("backtest.count", tags={"status": "started"})
    try:
        configured_code = get_settings().market_data_provider
        provider = ProviderRegistry((SyntheticMarketDataProvider(),)).resolve(configured_code)
        # The persisted schema version alone selects the path. A V2 definition is loaded and
        # fully validated here, before any market data is requested or any candle is read.
        loaded = load_versioned_definition(backtest)
        request = await _historical_request(session, backtest)
        dataset, candles = await _acquire_dataset(session, backtest, provider, request)
        await _attach_dataset(session, backtest_id, dataset)
        if loaded is None:  # V1: the unchanged reference engine
            result = EmaCrossoverReferenceEngine(provider.identifier).run(
                backtest.configuration_snapshot,
                backtest.backtest_configuration_snapshot,
                candles,
            )
        else:  # V2: the Phase 5 runtime, over the already-loaded canonical definition
            try:
                result = StrategyRuntimeEngine(
                    provider.identifier, str(backtest.strategy_version_id)
                ).run_canonical(
                    loaded.canonical,
                    backtest.backtest_configuration_snapshot,
                    candles,
                )
            except BacktestExecutionError:
                raise
            except Exception as exc:  # an unexpected runtime bug is not a market-data failure
                log_event("backtest_runtime_failed", level=logging.ERROR, exc_info=True, backtest_id=backtest_id)
                raise BacktestExecutionError("Strategy runtime failed", "strategy_runtime_failed") from exc
        if len(result.trades) > MAX_RESULT_TRADES:
            raise BacktestExecutionError("Backtest trade result exceeds its limit")
        if len(result.equity_curve) > MAX_RESULT_EQUITY_POINTS:
            raise BacktestExecutionError("Backtest equity result exceeds its limit")
    except (BacktestExecutionError, MarketDataError) as exc:
        error_code = getattr(exc, "code", "market_data_invalid_payload")
        log_event("backtest_failed", level=logging.WARNING, backtest_id=backtest_id, error_code=error_code)
        metrics.increment("backtest.count", tags={"status": "failed", "error_code": error_code})
        return await _mark_backtest_failed(session, backtest_id, str(exc), getattr(exc, "code", "market_data_invalid_payload"))
    except Exception:
        log_event("backtest_failed", level=logging.ERROR, exc_info=True, backtest_id=backtest_id, error_code="market_data_provider_unavailable")
        metrics.increment("backtest.count", tags={"status": "failed", "error_code": "market_data_provider_unavailable"})
        return await _mark_backtest_failed(
            session,
            backtest_id,
            "Backtest execution failed",
            "market_data_provider_unavailable",
        )

    completed = await _mark_backtest_completed(
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
    duration_ms = (time.perf_counter() - started) * 1000
    log_event("backtest_completed", backtest_id=backtest_id, dataset_id=completed.market_data_dataset_id, duration_ms=round(duration_ms, 3))
    metrics.increment("backtest.count", tags={"status": "completed"})
    metrics.observe("backtest.duration_ms", duration_ms, tags={"status": "completed"})
    return completed


def _snapshot_schema_version(strategy_version: StrategyVersion) -> int:
    """The version to snapshot. A missing value is a legacy V1 record; anything else is copied
    verbatim so an unsupported value fails deterministically at execution, never silently as V1."""
    value = getattr(strategy_version, "definition_schema_version", None)
    return LEGACY_SCHEMA_VERSION if value is None else value


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
    backtest.error_code = None
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
    error_code: str = "market_data_invalid_payload",
) -> Backtest:
    backtest = await _get_locked_backtest(session, backtest_id)
    backtest.status = BacktestStatus.FAILED
    backtest.completed_at = datetime.now(timezone.utc)
    backtest.result_summary = None
    backtest.error_message = _sanitize_error(error_message)
    backtest.error_code = error_code
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
            id="20000000-0000-4000-8000-000000000001",
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


async def _acquire_dataset(session, backtest, provider, request):
    settings = get_settings()
    if request.adjustment_policy != "unadjusted":
        raise MarketDataError("market_data_invalid_payload", "Only unadjusted market data is supported")
    if request.start and request.end and (request.end - request.start).days > settings.market_data_max_range_days:
        raise MarketDataError("market_data_invalid_payload", "Requested market data range exceeds configured limit")
    requested_start = request.sessions[0].local_session_date
    requested_end = request.sessions[-1].local_session_date
    mapping = None
    if provider.code != "synthetic":
        mapping = await resolve_mapping(session, uuid.UUID(request.instrument.id), provider.code, requested_start, requested_end)
        request.metadata["provider_mapping"] = {
            "id": str(mapping.id), "vendor_instrument_id": mapping.vendor_instrument_id,
            "vendor_symbol": mapping.vendor_symbol, "valid_from": mapping.valid_from.isoformat() if mapping.valid_from else None,
            "valid_to": mapping.valid_to.isoformat() if mapping.valid_to else None,
        }
    mapping_id = mapping.id if mapping else None
    key = dataset_key(request.instrument.id, provider.code, mapping_id, request.timeframe, request.adjustment_policy, requested_start, requested_end)
    existing = await session.scalar(select(MarketDataDataset).options(selectinload(MarketDataDataset.candles)).where(MarketDataDataset.dataset_key == key, MarketDataDataset.status == MarketDataDatasetStatus.READY))
    if existing is not None:
        candles = tuple(Candle(c.session_date, c.timestamp, c.open, c.high, c.low, c.close, c.volume) for c in existing.candles)
        if canonical_checksum(candles) != existing.normalized_checksum:
            log_event("market_data_checksum_failed", level=logging.WARNING, dataset_id=existing.id, provider_code=provider.code)
            metrics.increment("market_data.failures", tags={"error_code": "market_data_checksum_mismatch"})
            raise MarketDataError("market_data_checksum_mismatch", "Stored market data checksum does not match immutable candles")
        log_event("market_data_dataset_reused", dataset_id=existing.id, provider_code=provider.code, instrument_id=request.instrument.id)
        metrics.increment("market_data.datasets", tags={"result": "reused", "provider": provider.code})
        return existing, candles
    log_event("market_data_acquisition_started", provider_code=provider.code, instrument_id=request.instrument.id)
    batch = await load_with_policy(provider, request, timeout_seconds=settings.market_data_timeout_seconds, max_retries=settings.market_data_max_retries)
    candles, duplicate_count = validate_and_normalize(batch.candles, start=requested_start, end=requested_end, max_candles=settings.market_data_max_candles)
    checksum = canonical_checksum(candles)
    calendar = request.metadata.get("calendar") or {}
    missing_count = max(0, len(request.sessions) - len({c.session_date for c in candles}))
    provenance = {
        "provider_code": provider.code, "provider_adapter_version": provider.adapter_version,
        "product_feed_identifier": batch.dataset_reference, "instrument_id": request.instrument.id,
        "mapping_id": str(mapping_id) if mapping_id else None, "mapping_snapshot": request.metadata.get("provider_mapping"),
        "requested_range": {"start": requested_start.isoformat(), "end": requested_end.isoformat()},
        "actual_range": {"start": candles[0].session_date.isoformat(), "end": candles[-1].session_date.isoformat()},
        "timeframe": request.timeframe, "adjustment_policy": request.adjustment_policy,
        "candle_count": len(candles), "duplicate_count": duplicate_count, "missing_session_count": missing_count,
        "validation_policy_version": "daily-ohlcv-v1", "calendar_code": calendar.get("calendar_identifier"),
        "calendar_version": calendar.get("calendar_policy_version"), "exception_manifest_version": calendar.get("exception_manifest_version"),
        "source_timestamp_convention": "exchange-session-close-converted-to-utc" if request.timeframe == "1d" else "exchange-session-hour-utc",
        "raw_checksum": batch.provenance.get("raw_checksum"), "normalized_checksum": checksum,
        "synthetic": bool(batch.provenance.get("synthetic")),
    }
    if len(json.dumps(provenance, separators=(",", ":")).encode()) > 16384:
        raise MarketDataError("market_data_invalid_payload", "Market data provenance exceeds configured limit")
    dataset = MarketDataDataset(
        dataset_key=key, instrument_id=uuid.UUID(request.instrument.id), provider_code=provider.code,
        provider_mapping_id=mapping_id, timeframe=request.timeframe, adjustment_policy=request.adjustment_policy,
        requested_start=requested_start, requested_end=requested_end, actual_start=candles[0].session_date,
        actual_end=candles[-1].session_date, fetched_at=batch.fetched_at, candle_count=len(candles),
        raw_checksum=batch.provenance.get("raw_checksum"), normalized_checksum=checksum,
        status=MarketDataDatasetStatus.READY, provenance=provenance,
    )
    dataset.candles = [MarketDataCandle(session_date=c.session_date, timestamp=c.timestamp, open=c.open, high=c.high, low=c.low, close=c.close, volume=c.volume) for c in candles]
    session.add(dataset)
    await session.commit()
    await session.refresh(dataset)
    log_event("market_data_acquisition_completed", dataset_id=dataset.id, provider_code=provider.code, instrument_id=request.instrument.id)
    metrics.increment("market_data.datasets", tags={"result": "acquired", "provider": provider.code})
    return dataset, candles


async def _attach_dataset(session, backtest_id, dataset):
    backtest = await _get_locked_backtest(session, backtest_id)
    backtest.market_data_dataset_id = dataset.id
    backtest.market_data_provider = dataset.provider_code
    backtest.dataset_reference = str(dataset.id)
    backtest.timeframe = dataset.timeframe
    backtest.range_start = datetime.combine(dataset.actual_start, datetime.min.time(), timezone.utc)
    backtest.range_end = datetime.combine(dataset.actual_end, datetime.min.time(), timezone.utc)
    backtest.adjustment_policy = dataset.adjustment_policy
    backtest.data_fetched_at = dataset.fetched_at
    public_provenance = deepcopy(dataset.provenance)
    public_provenance.pop("mapping_id", None)
    public_provenance.pop("mapping_snapshot", None)
    backtest.market_data_provenance = public_provenance
    await session.commit()


def _require_utc(value: datetime, label: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise BacktestExecutionError(f"{label} must be UTC-aware")
