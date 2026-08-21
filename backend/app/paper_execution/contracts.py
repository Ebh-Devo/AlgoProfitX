from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, Sequence

from app.backtesting.contracts import Candle


@dataclass(frozen=True)
class PaperExecutionResult:
    signal: str
    execution_outcome: str
    no_fill_reason: str | None
    order: dict[str, str] | None
    fill: dict[str, str] | None
    position: dict[str, str | None]
    reference_instrument: dict[str, str | int]
    engine_identifier: str
    provider_identifier: str


class PaperMarketDataProvider(Protocol):
    identifier: str

    def load(self, configuration: dict) -> Sequence[Candle]: ...


class PaperExecutionAdapter(Protocol):
    identifier: str

    def execute(
        self,
        configuration: dict,
        notional_amount: Decimal,
        allocation_currency: str,
        candles: Sequence[Candle],
    ) -> PaperExecutionResult: ...


class PaperExecutionError(Exception):
    """An expected, non-sensitive deterministic paper-execution failure."""

    def __init__(self, error_code: str, message: str):
        self.error_code = error_code
        super().__init__(message)
