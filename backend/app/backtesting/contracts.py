from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class BacktestExecutionResult:
    initial_capital: Decimal
    final_equity: Decimal
    total_return: Decimal
    trades: tuple[dict[str, str], ...]
    equity_curve: tuple[dict[str, str], ...]
    engine_identifier: str
    provider_identifier: str


class BacktestEngine(Protocol):
    def run(
        self,
        configuration: dict,
        backtest_configuration: dict,
        candles: Sequence[Candle],
    ) -> BacktestExecutionResult: ...


class MarketDataProvider(Protocol):
    def load(
        self,
        configuration: dict,
        backtest_configuration: dict,
        reference: str | None,
    ) -> Sequence[Candle]: ...


class BacktestExecutionError(Exception):
    """An expected, safe-to-return reference execution failure."""
