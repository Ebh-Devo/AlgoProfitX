"""Market data for the runtime: validated bars, indicator series, and the evaluation context.

Indicator maths is *reused*, never re-implemented: ``ema@1`` delegates to the existing
reference calculation (SMA-seeded, ``None`` during warm-up). The series are causal (value at
``t`` depends only on bars ``<= t``), and ``BarCursorContext`` can only read offsets ``<= 0``
from its cursor, so a bar after ``t`` is unreachable from an evaluation at ``t``.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable, Iterator, Mapping, Sequence

from app.backtesting.contracts import Candle
from app.backtesting.reference import EmaCrossoverReferenceEngine
from app.strategy_definition.evaluator import operand_key
from app.strategy_definition.evaluator.context import PRICE_FIELDS, check_decimal, check_offset
from app.strategy_definition.evaluator.errors import (
    InvalidEvaluationRequestError,
    MissingContextValueError,
)
from app.strategy_definition.runtime.errors import RuntimeDataError, RuntimeSetupError
from app.strategy_definition.schema import (
    AllCondition,
    AnyCondition,
    CompareCondition,
    CrossCondition,
    EdgeCondition,
    IndicatorRef,
    NotCondition,
    PriceOperand,
    StrategyDefinition,
)

Series = tuple["Decimal | None", ...]


def validate_candles(candles: Sequence[Candle]) -> None:
    """Non-empty, UTC-aware and strictly increasing (spec §17.10)."""
    if not candles:
        raise RuntimeDataError("candle data is empty")
    previous: datetime | None = None
    for candle in candles:
        stamp = candle.timestamp
        if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
            raise RuntimeDataError("candle timestamps must be UTC-aware")
        if previous is not None and stamp <= previous:
            raise RuntimeDataError("candle timestamps must be strictly increasing")
        previous = stamp


def _ema_value(values: Sequence[Decimal], params: Mapping[str, object]) -> Series:
    return EmaCrossoverReferenceEngine._ema(values, params["period"])


# (name, version) -> calculation over a price series. Only what already exists is registered.
CALCULATORS: Mapping[tuple[str, int], Callable[[Sequence[Decimal], Mapping[str, object]], Series]] = {
    ("ema", 1): _ema_value,
}


def indicator_refs(definition: StrategyDefinition) -> tuple[IndicatorRef, ...]:
    """Every distinct indicator operand in the rules, in first-appearance order."""
    found: dict[str, IndicatorRef] = {}

    def walk(node: object) -> Iterator[IndicatorRef]:
        if isinstance(node, (AllCondition, AnyCondition)):
            for child in node.of:
                yield from walk(child)
        elif isinstance(node, (NotCondition, EdgeCondition)):
            yield from walk(node.of)
        elif isinstance(node, (CompareCondition, CrossCondition)):
            yield from walk(node.left)
            yield from walk(node.right)
        elif isinstance(node, IndicatorRef):
            yield node
            if node.source is not None:
                yield from walk(node.source)

    for rule in definition.rules:
        for ref in walk(rule.when):
            found.setdefault(operand_key(ref), ref)
    return tuple(found.values())


def compute_indicator_series(
    definition: StrategyDefinition, candles: Sequence[Candle]
) -> dict[str, Series]:
    """``operand_key -> series`` aligned with ``candles`` for every indicator the rules use."""
    series: dict[str, Series] = {}
    for ref in indicator_refs(definition):
        calculator = CALCULATORS.get((ref.name, ref.version))
        if calculator is None:
            raise RuntimeSetupError(f"indicator {ref.name}@{ref.version} has no runtime calculation")
        if ref.timeframe != definition.timeframe:
            raise RuntimeSetupError("indicators on another timeframe are not supported")
        if not isinstance(ref.source, PriceOperand) or ref.source.field == "volume":
            raise RuntimeSetupError("indicator sources must be a price field in this runtime")
        values = [getattr(candle, ref.source.field) for candle in candles]
        series[operand_key(ref)] = calculator(values, ref.params)
    return series


class BarCursorContext:
    """The evaluator's window at bar ``index``: offsets ``<= 0`` only, nothing after it."""

    def __init__(
        self,
        candles: Sequence[Candle],
        indicators: Mapping[str, Series],
        index: int,
    ) -> None:
        if not 0 <= index < len(candles):
            raise InvalidEvaluationRequestError("cursor is outside the candle range")
        self._candles = candles
        self._indicators = indicators
        self._index = index

    @property
    def timestamp(self) -> datetime:
        return self._candles[self._index].timestamp

    def _position(self, offset: int) -> int | None:
        check_offset(offset)
        position = self._index + offset
        return position if position >= 0 else None

    def price(self, field: str, offset: int) -> Decimal | None:
        if field not in PRICE_FIELDS:
            raise InvalidEvaluationRequestError(f"unknown price field {field!r}")
        position = self._position(offset)
        if position is None:
            return None
        value = getattr(self._candles[position], field)
        return check_decimal(None if value is None else Decimal(value))

    def indicator(self, ref: IndicatorRef, offset: int) -> Decimal | None:
        key = operand_key(ref)
        series = self._indicators.get(key)
        if series is None:
            raise MissingContextValueError(f"no computed series for indicator {key}")
        position = self._position(offset)
        return None if position is None else series[position]
