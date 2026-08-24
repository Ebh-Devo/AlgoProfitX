from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Sequence

from app.backtesting.contracts import (
    BacktestExecutionError,
    BacktestExecutionResult,
    Candle,
    HistoricalCandleRequest,
    MarketDataBatch,
)


class SyntheticMarketDataProvider:
    """Fixed local candles for deterministic reference-engine validation."""

    identifier = "synthetic-local-v1"
    max_candles = 64

    def load(self, request: HistoricalCandleRequest) -> MarketDataBatch:
        reference = request.metadata.get("requested_reference")
        if reference not in (None, self.identifier):
            raise BacktestExecutionError("Unsupported synthetic data reference")
        if request.instrument.canonical_symbol != "TRADEEBH_TEST_EQ":
            raise BacktestExecutionError("Unsupported synthetic Instrument")
        if request.timeframe != "1h":
            raise BacktestExecutionError("Synthetic provider supports only timeframe=1h")
        if request.adjustment_policy != "unadjusted":
            raise BacktestExecutionError("Synthetic provider supports only unadjusted data")

        start = request.start or datetime(2025, 1, 1, tzinfo=timezone.utc)
        self._require_utc(start, "Historical request start")
        if request.end is not None:
            self._require_utc(request.end, "Historical request end")
            if request.end < start:
                raise BacktestExecutionError("Historical request end precedes start")
        closes = self._closes()
        if len(closes) > self.max_candles:
            raise BacktestExecutionError("Synthetic dataset exceeds its limit")

        timestamps = tuple(
            timestamp
            for session in request.sessions
            for timestamp in self._session_timestamps(
                session.open_utc, session.close_utc
            )
        )[: len(closes)]
        if len(timestamps) < len(closes):
            raise BacktestExecutionError(
                "Historical request has insufficient trading-session coverage"
            )
        candles = tuple(
            Candle(
                timestamp=timestamps[index],
                open=close,
                high=close + Decimal("0.5"),
                low=close - Decimal("0.5"),
                close=close,
                volume=Decimal("1000"),
            )
            for index, close in enumerate(closes)
        )
        return MarketDataBatch(
            candles=candles,
            provider_code=self.identifier,
            dataset_reference="synthetic-reference-candles-v1",
            fetched_at=datetime.now(timezone.utc),
            timeframe=request.timeframe,
            actual_range_start=candles[0].timestamp,
            actual_range_end=candles[-1].timestamp,
            adjustment_policy=request.adjustment_policy,
            provenance={
                "generator": "tradeebh-deterministic-reference",
                "generator_version": 1,
                "candle_count": len(candles),
                "synthetic": True,
                "calendar": request.metadata.get("calendar"),
            },
        )

    @staticmethod
    def _session_timestamps(
        open_utc: datetime, close_utc: datetime
    ) -> tuple[datetime, ...]:
        timestamps: list[datetime] = []
        current = open_utc
        while current < close_utc:
            timestamps.append(current)
            current += timedelta(hours=1)
        return tuple(timestamps)

    @staticmethod
    def _require_utc(value: datetime, label: str) -> None:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise BacktestExecutionError(f"{label} must be UTC-aware")

    @staticmethod
    def _closes() -> tuple[Decimal, ...]:
        descending = tuple(Decimal("128") - Decimal(index) for index in range(28))
        ascending = tuple(Decimal("101") + Decimal(index) for index in range(36))
        return descending + ascending


class EmaCrossoverReferenceEngine:
    """A one-long-trade EMA crossover reference, not a general strategy engine."""

    identifier = "ema-crossover-reference-v1"

    def __init__(self, provider_identifier: str):
        self._provider_identifier = provider_identifier

    def run(
        self,
        configuration: dict,
        backtest_configuration: dict,
        candles: Sequence[Candle],
    ) -> BacktestExecutionResult:
        self._validate_candles(candles)
        fast_period, slow_period = self._periods(configuration)
        initial_capital = self._initial_capital(backtest_configuration)

        closes = [candle.close for candle in candles]
        fast_ema = self._ema(closes, fast_period)
        slow_ema = self._ema(closes, slow_period)
        entry_index = self._entry_index(fast_ema, slow_ema)

        quantity = Decimal("0")
        entry_price: Decimal | None = None
        if entry_index is not None:
            entry_price = candles[entry_index].close
            quantity = initial_capital / entry_price

        equity_curve = tuple(
            {
                "timestamp": candle.timestamp.isoformat(),
                "equity": self._decimal_string(
                    initial_capital
                    if entry_index is None or index < entry_index
                    else quantity * candle.close
                ),
            }
            for index, candle in enumerate(candles)
        )

        final_equity = (
            initial_capital
            if entry_index is None
            else quantity * candles[-1].close
        )
        trades: tuple[dict[str, str], ...] = ()
        if entry_index is not None and entry_price is not None:
            trades = (
                {
                    "side": "long",
                    "entry_timestamp": candles[entry_index].timestamp.isoformat(),
                    "exit_timestamp": candles[-1].timestamp.isoformat(),
                    "quantity": self._decimal_string(quantity),
                    "entry_price": self._decimal_string(entry_price),
                    "exit_price": self._decimal_string(candles[-1].close),
                    "pnl": self._decimal_string(final_equity - initial_capital),
                },
            )

        return BacktestExecutionResult(
            initial_capital=initial_capital,
            final_equity=final_equity,
            total_return=(final_equity - initial_capital) / initial_capital * Decimal("100"),
            trades=trades,
            equity_curve=equity_curve,
            engine_identifier=self.identifier,
            provider_identifier=self._provider_identifier,
        )

    @staticmethod
    def _validate_candles(candles: Sequence[Candle]) -> None:
        if not candles:
            raise BacktestExecutionError("Synthetic candle data is empty")
        previous_timestamp: datetime | None = None
        for candle in candles:
            if candle.timestamp.tzinfo is None:
                raise BacktestExecutionError("Candle timestamps must be UTC-aware")
            if candle.timestamp.utcoffset() != timezone.utc.utcoffset(candle.timestamp):
                raise BacktestExecutionError("Candle timestamps must be UTC")
            if previous_timestamp is not None and candle.timestamp <= previous_timestamp:
                raise BacktestExecutionError("Candle timestamps must be ordered")
            previous_timestamp = candle.timestamp

    @staticmethod
    def _periods(configuration: dict) -> tuple[int, int]:
        entry = configuration.get("entry")
        if not isinstance(entry, dict) or entry.get("type") != "ema_crossover":
            raise BacktestExecutionError(
                "Reference engine supports only entry.type=ema_crossover"
            )
        try:
            fast_period = int(entry["fast_period"])
            slow_period = int(entry["slow_period"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BacktestExecutionError("EMA periods must be positive integers") from exc
        if fast_period <= 0 or slow_period <= fast_period:
            raise BacktestExecutionError("EMA periods must satisfy 0 < fast < slow")
        return fast_period, slow_period

    @staticmethod
    def _initial_capital(backtest_configuration: dict) -> Decimal:
        try:
            value = Decimal(str(backtest_configuration["initial_capital"]))
        except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
            raise BacktestExecutionError("initial_capital must be a positive number") from exc
        if value <= 0:
            raise BacktestExecutionError("initial_capital must be a positive number")
        return value

    @staticmethod
    def _ema(closes: Sequence[Decimal], period: int) -> tuple[Decimal | None, ...]:
        multiplier = Decimal("2") / Decimal(period + 1)
        ema: Decimal | None = None
        values: list[Decimal | None] = []
        for index, close in enumerate(closes):
            if index < period - 1:
                values.append(None)
                continue
            if ema is None:
                ema = sum(closes[index - period + 1 : index + 1]) / Decimal(period)
            else:
                ema = (close - ema) * multiplier + ema
            values.append(ema)
        return tuple(values)

    @staticmethod
    def _entry_index(
        fast_ema: Sequence[Decimal | None],
        slow_ema: Sequence[Decimal | None],
    ) -> int | None:
        for index in range(1, len(fast_ema)):
            previous_fast = fast_ema[index - 1]
            previous_slow = slow_ema[index - 1]
            current_fast = fast_ema[index]
            current_slow = slow_ema[index]
            if (
                previous_fast is not None
                and previous_slow is not None
                and current_fast is not None
                and current_slow is not None
                and previous_fast <= previous_slow
                and current_fast > current_slow
            ):
                return index
        return None

    @staticmethod
    def _decimal_string(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.00000001")), "f")
