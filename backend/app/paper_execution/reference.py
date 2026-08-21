from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Sequence

from app.backtesting.contracts import Candle
from app.paper_execution.contracts import (
    PaperExecutionError,
    PaperExecutionResult,
)


QUANTITY_QUANTUM = Decimal("0.00000001")
SUPPORTED_INSTRUMENT = "XAUUSD"


class SyntheticPaperMarketDataProvider:
    """Fixed, local candles used only by the paper-execution reference contract."""

    identifier = "synthetic-paper-local-v1"
    max_candles = 64

    def load(self, configuration: dict) -> Sequence[Candle]:
        scenario = configuration.get("paper_execution_scenario", "latest_crossover")
        closes = self._closes(scenario)
        if len(closes) > self.max_candles:
            raise PaperExecutionError(
                "provider_reference_data_failure",
                "Synthetic paper dataset exceeds its limit",
            )

        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
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
    def _closes(scenario: object) -> tuple[Decimal, ...]:
        if scenario == "latest_crossover":
            return tuple(Decimal(value) for value in (10, 9, 8, 7, 6, 5, 6, 7, 8))
        if scenario == "historical_crossover":
            return tuple(
                Decimal(value)
                for value in (10, 9, 8, 7, 6, 5, 6, 7, 8, 9, 10, 11, 12)
            )
        if scenario == "no_signal":
            return (Decimal("10"),) * 12
        raise PaperExecutionError(
            "invalid_strategy_configuration",
            "Unsupported paper execution reference scenario",
        )


class EmaCrossoverPaperAdapter:
    """One-buy-only, latest-candle EMA reference adapter; not a general strategy engine.

    Quantity is notional divided by the deterministic latest close, rounded down to
    eight decimal places to match the persisted NUMERIC(18, 8) capital precision.
    """

    identifier = "ema-crossover-paper-reference-v1"

    def __init__(self, provider_identifier: str):
        self._provider_identifier = provider_identifier

    def execute(
        self,
        configuration: dict,
        notional_amount: Decimal,
        candles: Sequence[Candle],
    ) -> PaperExecutionResult:
        if configuration.get("instrument") != SUPPORTED_INSTRUMENT:
            raise PaperExecutionError(
                "unsupported_instrument",
                "Paper execution supports only instrument XAUUSD",
            )
        fast_period, slow_period = self._periods(configuration)
        self._validate_candles(candles)
        if notional_amount <= 0:
            raise PaperExecutionError(
                "execution_calculation_failure",
                "Paper execution notional amount must be positive",
            )

        closes = [candle.close for candle in candles]
        fast = self._ema(closes, fast_period)
        slow = self._ema(closes, slow_period)
        latest_index = len(candles) - 1
        signal = self._latest_buy_signal(fast, slow, latest_index)
        if not signal:
            return PaperExecutionResult(
                signal="none",
                order=None,
                fill=None,
                position={"quantity": self._decimal_string(Decimal("0")), "average_price": None},
                engine_identifier=self.identifier,
                provider_identifier=self._provider_identifier,
            )

        fill_price = candles[latest_index].close
        quantity = (notional_amount / fill_price).quantize(
            QUANTITY_QUANTUM,
            rounding=ROUND_DOWN,
        )
        if quantity <= 0:
            raise PaperExecutionError(
                "execution_calculation_failure",
                "Paper execution quantity rounds to zero",
            )
        timestamp = candles[latest_index].timestamp.isoformat()
        order = {
            "side": "buy",
            "quantity": self._decimal_string(quantity),
            "requested_price": self._decimal_string(fill_price),
            "reference_price": self._decimal_string(fill_price),
            "timestamp": timestamp,
        }
        fill = {
            "quantity": self._decimal_string(quantity),
            "price": self._decimal_string(fill_price),
            "timestamp": timestamp,
        }
        return PaperExecutionResult(
            signal="buy",
            order=order,
            fill=fill,
            position={
                "quantity": self._decimal_string(quantity),
                "average_price": self._decimal_string(fill_price),
            },
            engine_identifier=self.identifier,
            provider_identifier=self._provider_identifier,
        )

    @staticmethod
    def _validate_candles(candles: Sequence[Candle]) -> None:
        if not candles:
            raise PaperExecutionError(
                "provider_reference_data_failure",
                "Synthetic paper candle data is empty",
            )
        previous_timestamp: datetime | None = None
        for candle in candles:
            if candle.timestamp.tzinfo is None or candle.timestamp.utcoffset() != timezone.utc.utcoffset(candle.timestamp):
                raise PaperExecutionError(
                    "provider_reference_data_failure",
                    "Synthetic paper candle timestamps must be UTC-aware",
                )
            if previous_timestamp is not None and candle.timestamp <= previous_timestamp:
                raise PaperExecutionError(
                    "provider_reference_data_failure",
                    "Synthetic paper candle timestamps must be ordered",
                )
            previous_timestamp = candle.timestamp

    @staticmethod
    def _periods(configuration: dict) -> tuple[int, int]:
        entry = configuration.get("entry")
        if not isinstance(entry, dict) or entry.get("type") != "ema_crossover":
            raise PaperExecutionError(
                "invalid_strategy_configuration",
                "Paper reference adapter supports only entry.type=ema_crossover",
            )
        try:
            fast_period = int(entry["fast_period"])
            slow_period = int(entry["slow_period"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PaperExecutionError(
                "invalid_strategy_configuration",
                "EMA periods must be positive integers",
            ) from exc
        if fast_period <= 0 or slow_period <= fast_period:
            raise PaperExecutionError(
                "invalid_strategy_configuration",
                "EMA periods must satisfy 0 < fast < slow",
            )
        return fast_period, slow_period

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
    def _latest_buy_signal(
        fast: Sequence[Decimal | None],
        slow: Sequence[Decimal | None],
        latest_index: int,
    ) -> bool:
        if latest_index < 1:
            return False
        previous_fast, previous_slow = fast[latest_index - 1], slow[latest_index - 1]
        current_fast, current_slow = fast[latest_index], slow[latest_index]
        return (
            previous_fast is not None
            and previous_slow is not None
            and current_fast is not None
            and current_slow is not None
            and previous_fast <= previous_slow
            and current_fast > current_slow
        )

    @staticmethod
    def _decimal_string(value: Decimal) -> str:
        return format(value.quantize(QUANTITY_QUANTUM), "f")
