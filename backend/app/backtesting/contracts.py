from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, Sequence

from app.market_calendar.contracts import TradingSession


@dataclass(frozen=True)
class Candle:
    session_date: date
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None


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
    exchange_timezone: str
    exchange_is_active: bool


@dataclass(frozen=True)
class HistoricalCandleRequest:
    instrument: InstrumentIdentity
    timeframe: str
    start: datetime | None
    end: datetime | None
    adjustment_policy: str
    sessions: tuple[TradingSession, ...]
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
    code: str
    adapter_version: str

    async def load(self, request: HistoricalCandleRequest) -> MarketDataBatch: ...


class BacktestExecutionError(Exception):
    """An expected, safe-to-return reference execution failure."""

    def __init__(self, message: str, code: str = "market_data_invalid_payload"):
        super().__init__(message)
        self.code = code
