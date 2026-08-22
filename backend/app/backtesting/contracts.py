from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class InstrumentIdentity:
    id: str | None
    canonical_symbol: str
    exchange_symbol: str
    name: str
    exchange_code: str
    instrument_type: str
    quote_currency: str
    tick_size: str | None
    lot_size: int | None
    is_tradeable: bool


@dataclass(frozen=True)
class HistoricalCandleRequest:
    instrument: InstrumentIdentity
    timeframe: str
    start: datetime | None
    end: datetime | None
    adjustment_policy: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MarketDataBatch:
    candles: tuple[Candle, ...]
    provider_code: str
    dataset_reference: str
    fetched_at: datetime
    timeframe: str
    actual_range_start: datetime
    actual_range_end: datetime
    adjustment_policy: str
    provenance: dict[str, Any]


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


class HistoricalMarketDataProvider(Protocol):
    def load(self, request: HistoricalCandleRequest) -> MarketDataBatch: ...


class BacktestExecutionError(Exception):
    """An expected, safe-to-return reference execution failure."""
