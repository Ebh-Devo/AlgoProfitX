from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Sequence

from app.backtesting.contracts import Candle
from app.paper_execution.contracts import (
    PaperExecutionError,
    PaperExecutionResult,
)


PRICE_QUANTUM = Decimal("0.01")


@dataclass(frozen=True)
class PaperReferenceInstrument:
    """Synthetic NSE cash-equity fixture; it is not a real listed security."""

    market: str
    symbol: str
    instrument_type: str
    quote_currency: str
    exchange_timezone: str
    lot_size: int
    tick_size: Decimal

    def metadata(self) -> dict[str, str | int]:
        return {
            "market": self.market,
            "symbol": self.symbol,
            "instrument_type": self.instrument_type,
            "quote_currency": self.quote_currency,
            "exchange_timezone": self.exchange_timezone,
            "lot_size": self.lot_size,
            "tick_size": format(self.tick_size, "f"),
        }


REFERENCE_INSTRUMENT = PaperReferenceInstrument(
    market="NSE",
    symbol="TRADEEBH_TEST_EQ",
    instrument_type="equity",
    quote_currency="INR",
    exchange_timezone="Asia/Kolkata",
    lot_size=1,
    tick_size=PRICE_QUANTUM,
)


class SyntheticPaperMarketDataProvider:
    """Fixed local data for the synthetic NSE reference contract, never real NSE data."""

    identifier = "synthetic-paper-nse-equity-v1"
    max_candles = 64

    def load(self, configuration: dict) -> Sequence[Candle]:
        scenario = configuration.get("paper_execution_scenario", "latest_crossover")
        closes = self._closes(scenario)
        if len(closes) > self.max_candles:
            raise PaperExecutionError(
                "provider_reference_data_failure",
                "Synthetic paper dataset exceeds its limit",
            )

        # NSE-style 09:15 local time represented canonically as 03:45 UTC.
        local_start = datetime(
            2025,
            1,
            1,
            9,
            15,
            tzinfo=timezone(timedelta(hours=5, minutes=30)),
        )
        start = local_start.astimezone(timezone.utc)
        return tuple(
            Candle(
                timestamp=start + timedelta(hours=index),
                open=close,
                high=close + REFERENCE_INSTRUMENT.tick_size,
                low=close - REFERENCE_INSTRUMENT.tick_size,
                close=close,
                volume=Decimal("1000"),
            )
            for index, close in enumerate(closes)
        )

    @staticmethod
    def _closes(scenario: object) -> tuple[Decimal, ...]:
        if scenario == "latest_crossover":
            return tuple(
                Decimal(value)
                for value in (110, 109, 108, 107, 106, 105, 106, 107, 108)
            )
        if scenario == "historical_crossover":
            return tuple(
                Decimal(value)
                for value in (
                    110,
                    109,
                    108,
                    107,
                    106,
                    105,
                    106,
                    107,
                    108,
                    109,
                    110,
                    111,
                    112,
                )
            )
        if scenario == "no_signal":
            return (Decimal("100"),) * 12
        raise PaperExecutionError(
            "invalid_strategy_configuration",
            "Unsupported paper execution reference scenario",
        )


class EmaCrossoverPaperAdapter:
    """One-buy-only latest-candle EMA reference adapter; not a general strategy engine.

    Quantity follows the cash-equity, lot-aware formula
    floor((notional / price) / lot_size) * lot_size. The synthetic fixture has a
    lot size of one, so all filled quantities are whole shares.
    """

    identifier = "ema-crossover-paper-reference-v1"

    def __init__(self, provider_identifier: str):
        self._provider_identifier = provider_identifier

    def execute(
        self,
        configuration: dict,
        notional_amount: Decimal,
        allocation_currency: str,
        candles: Sequence[Candle],
    ) -> PaperExecutionResult:
        if configuration.get("instrument") != REFERENCE_INSTRUMENT.symbol:
            raise PaperExecutionError(
                "unsupported_instrument",
                "Paper execution supports only synthetic instrument TRADEEBH_TEST_EQ",
            )
        if allocation_currency != REFERENCE_INSTRUMENT.quote_currency:
            raise PaperExecutionError(
                "unsupported_currency",
                "Paper execution supports only allocation currency INR",
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
            return self._no_fill_result("none", "no_signal", None)

        fill_price = candles[latest_index].close
        quantity = self._quantity_for_notional(notional_amount, fill_price)
        if quantity <= 0:
            return self._no_fill_result(
                "buy",
                "no_fill",
                "insufficient_notional_for_one_share",
            )

        timestamp = candles[latest_index].timestamp.isoformat()
        order = {
            "side": "buy",
            "quantity": self._quantity_string(quantity),
            "requested_price": self._price_string(fill_price),
            "reference_price": self._price_string(fill_price),
            "timestamp": timestamp,
        }
        fill = {
            "quantity": self._quantity_string(quantity),
            "price": self._price_string(fill_price),
            "timestamp": timestamp,
        }
        return PaperExecutionResult(
            signal="buy",
            execution_outcome="filled",
            no_fill_reason=None,
            order=order,
            fill=fill,
            position={
                "quantity": self._quantity_string(quantity),
                "average_price": self._price_string(fill_price),
            },
            reference_instrument=REFERENCE_INSTRUMENT.metadata(),
            engine_identifier=self.identifier,
            provider_identifier=self._provider_identifier,
        )

    def _no_fill_result(
        self,
        signal: str,
        execution_outcome: str,
        no_fill_reason: str | None,
    ) -> PaperExecutionResult:
        return PaperExecutionResult(
            signal=signal,
            execution_outcome=execution_outcome,
            no_fill_reason=no_fill_reason,
            order=None,
            fill=None,
            position={"quantity": "0", "average_price": None},
            reference_instrument=REFERENCE_INSTRUMENT.metadata(),
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
    def _quantity_for_notional(notional_amount: Decimal, fill_price: Decimal) -> Decimal:
        lot_size = Decimal(REFERENCE_INSTRUMENT.lot_size)
        whole_lots = (notional_amount / fill_price / lot_size).to_integral_value(
            rounding=ROUND_DOWN,
        )
        return whole_lots * lot_size

    @staticmethod
    def _quantity_string(value: Decimal) -> str:
        return format(value.quantize(Decimal("1")), "f")

    @staticmethod
    def _price_string(value: Decimal) -> str:
        return format(value.quantize(REFERENCE_INSTRUMENT.tick_size), "f")
