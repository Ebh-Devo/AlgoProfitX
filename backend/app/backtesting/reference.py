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
from app.instrument_identity import is_synthetic_equity_symbol
from app.strategy_rules import (
    StrategyRuleError,
    parse_entry_rule,
    parse_exit_rule,
    require_closing_action,
)


class SyntheticMarketDataProvider:
    """Fixed local candles for deterministic reference-engine validation."""

    identifier = "synthetic-local-v1"
    code = "synthetic"
    adapter_version = "1"
    max_candles = 64

    async def load(self, request: HistoricalCandleRequest) -> MarketDataBatch:
        reference = request.metadata.get("requested_reference")
        if reference not in (None, self.identifier):
            raise BacktestExecutionError("Unsupported synthetic data reference")
        if not is_synthetic_equity_symbol(request.instrument.canonical_symbol):
            raise BacktestExecutionError("Unsupported synthetic Instrument")
        if request.timeframe != "1d":
            raise BacktestExecutionError("Synthetic provider supports only timeframe=1d")
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

        timestamps = tuple(session.close_utc for session in request.sessions)[: len(closes)]
        if len(timestamps) < len(closes):
            raise BacktestExecutionError(
                "Historical request has insufficient trading-session coverage"
            )
        candles = tuple(
            Candle(
                session_date=request.sessions[index].local_session_date,
                timestamp=timestamps[index],
                open=close,
                high=close + Decimal("0.5"),
                low=close - Decimal("0.5"),
                close=close,
                volume=1000,
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
                "generator": "algoprofitx-deterministic-reference",
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
    """A single-position EMA crossover reference, not a general strategy engine.

    V1 is intentionally limited: one entry rule, an optional exit rule, one trade. The entry
    action sets the side (buy opens a long, sell opens a short); the exit closes it.
    """

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
        try:
            entry_rule = parse_entry_rule(configuration)
            exit_rule = parse_exit_rule(configuration)
            if exit_rule is not None:
                require_closing_action(entry_rule.action, exit_rule.action)
        except StrategyRuleError as exc:
            raise BacktestExecutionError(str(exc)) from exc
        initial_capital = self._initial_capital(backtest_configuration)
        sign = Decimal("1") if entry_rule.action == "buy" else Decimal("-1")

        closes = [candle.close for candle in candles]
        entry_index = self._cross_index(
            self._ema(closes, entry_rule.fast_period),
            self._ema(closes, entry_rule.slow_period),
            entry_rule.direction,
            1,
        )

        # Optional exit rule: the first cross after entry. Entry-only configurations hold
        # to the final candle.
        exit_index = len(candles) - 1
        if entry_index is not None and exit_rule is not None:
            crossed = self._cross_index(
                self._ema(closes, exit_rule.fast_period),
                self._ema(closes, exit_rule.slow_period),
                exit_rule.direction,
                entry_index + 1,
            )
            if crossed is not None:
                exit_index = crossed

        quantity = Decimal("0")
        entry_price: Decimal | None = None
        if entry_index is not None:
            entry_price = candles[entry_index].close
            quantity = initial_capital / entry_price

        def equity_at(price: Decimal) -> Decimal:
            # Long gains when price rises, short when it falls: sign * (price - entry).
            return initial_capital + sign * quantity * (price - entry_price)

        equity_curve = tuple(
            {
                "timestamp": candle.timestamp.isoformat(),
                "equity": self._decimal_string(
                    initial_capital
                    if entry_index is None or index < entry_index
                    else equity_at(candles[min(index, exit_index)].close)
                ),
            }
            for index, candle in enumerate(candles)
        )

        final_equity = (
            initial_capital
            if entry_index is None
            else equity_at(candles[exit_index].close)
        )
        trades: tuple[dict[str, str], ...] = ()
        if entry_index is not None and entry_price is not None:
            trades = (
                {
                    "side": "long" if sign > 0 else "short",
                    "entry_timestamp": candles[entry_index].timestamp.isoformat(),
                    "exit_timestamp": candles[exit_index].timestamp.isoformat(),
                    "quantity": self._decimal_string(quantity),
                    "entry_price": self._decimal_string(entry_price),
                    "exit_price": self._decimal_string(candles[exit_index].close),
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
    def _cross_index(
        fast_ema: Sequence[Decimal | None],
        slow_ema: Sequence[Decimal | None],
        direction: str,
        start: int,
    ) -> int | None:
        """First index >= start where the fast EMA crosses the slow EMA in `direction`."""
        for index in range(max(start, 1), len(fast_ema)):
            previous_fast = fast_ema[index - 1]
            previous_slow = slow_ema[index - 1]
            current_fast = fast_ema[index]
            current_slow = slow_ema[index]
            if (
                previous_fast is None
                or previous_slow is None
                or current_fast is None
                or current_slow is None
            ):
                continue
            if direction == "above" and previous_fast <= previous_slow and current_fast > current_slow:
                return index
            if direction == "below" and previous_fast >= previous_slow and current_fast < current_slow:
                return index
        return None

    @staticmethod
    def _decimal_string(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.00000001")), "f")
