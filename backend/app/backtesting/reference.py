from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Sequence

from app.backtesting.contracts import (
    BacktestExecutionError,
    BacktestExecutionResult,
    Candle,
)


class SyntheticMarketDataProvider:
    """Fixed local candles for deterministic reference-engine validation."""

    identifier = "synthetic-local-v1"
    max_candles = 64

    def load(
        self,
        configuration: dict,
        backtest_configuration: dict,
        reference: str | None,
    ) -> Sequence[Candle]:
        if reference not in (None, self.identifier):
            raise BacktestExecutionError("Unsupported synthetic data reference")

        start = self._start_timestamp(backtest_configuration)
        closes = self._closes()
        if len(closes) > self.max_candles:
            raise BacktestExecutionError("Synthetic dataset exceeds its limit")

        return tuple(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=close,
                high=close + Decimal("0.5"),
                low=close - Decimal("0.5"),
                close=close,
                volume=Decimal("1000"),
            )
            for index, close in enumerate(closes)
        )

    @staticmethod
    def _start_timestamp(backtest_configuration: dict) -> datetime:
        start_date = backtest_configuration.get("start_date")
        if start_date is None:
            return datetime(2025, 1, 1, tzinfo=timezone.utc)

        try:
            parsed = datetime.fromisoformat(str(start_date).replace("Z", "+00:00"))
        except ValueError as exc:
            raise BacktestExecutionError("Invalid synthetic start_date") from exc

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

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
