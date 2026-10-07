"""Evaluation context: the only window the evaluator has onto market values.

Access is relative to the evaluation bar ``t``: offset ``0`` is ``t``, ``-1`` is ``t-1``.
Positive offsets are rejected, and ``HistoricalContext`` is built only from bars up to ``t``,
so a future bar cannot be reached. ``None`` means undefined (warm-up, missing data).
"""

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Protocol, Sequence

from app.strategy_definition.evaluator.errors import (
    InvalidEvaluationRequestError,
    MissingContextValueError,
)
from app.strategy_definition.schema import IndicatorRef, Operand

PRICE_FIELDS = ("open", "high", "low", "close", "volume")


class EvaluationContext(Protocol):
    """Narrow, offset-based view of values available at the evaluation bar."""

    @property
    def timestamp(self) -> datetime: ...

    def price(self, field: str, offset: int) -> Decimal | None: ...

    def indicator(self, ref: IndicatorRef, offset: int) -> Decimal | None: ...


def operand_key(operand: Operand) -> str:
    """Canonical, deterministic key of an operand (output included for indicators)."""
    return json.dumps(operand.to_dict(), sort_keys=True, separators=(",", ":"))


def check_offset(offset: int) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int):
        raise InvalidEvaluationRequestError(f"offset must be an int, got {offset!r}")
    if offset > 0:
        raise InvalidEvaluationRequestError(
            f"offset {offset} would read a future bar; only offsets <= 0 are allowed"
        )


def check_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite():
        raise InvalidEvaluationRequestError(f"values must be finite Decimal or None, got {value!r}")
    return value


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal | None = None


class HistoricalContext:
    """Bars and computed indicator series, ending at (and including) the evaluation bar.

    ``indicators`` maps ``operand_key(indicator_ref)`` to a series aligned one-to-one with
    ``bars``. Holding no bar after ``t`` is what makes lookahead impossible.
    """

    def __init__(
        self,
        bars: Sequence[Bar],
        indicators: Mapping[str, Sequence[Decimal | None]] | None = None,
    ):
        if not bars:
            raise InvalidEvaluationRequestError("a context needs at least the current bar")
        self._bars = tuple(bars)
        for bar in self._bars:
            for field in PRICE_FIELDS:
                check_decimal(getattr(bar, field))
        self._indicators: dict[str, tuple[Decimal | None, ...]] = {}
        for key, series in (indicators or {}).items():
            values = tuple(check_decimal(value) for value in series)
            if len(values) != len(self._bars):
                raise InvalidEvaluationRequestError(
                    f"indicator series {key} has {len(values)} values for {len(self._bars)} bars"
                )
            self._indicators[key] = values

    @property
    def timestamp(self) -> datetime:
        return self._bars[-1].timestamp

    def _index(self, offset: int) -> int | None:
        check_offset(offset)
        index = len(self._bars) - 1 + offset
        return index if index >= 0 else None

    def price(self, field: str, offset: int) -> Decimal | None:
        if field not in PRICE_FIELDS:
            raise InvalidEvaluationRequestError(f"unknown price field {field!r}")
        index = self._index(offset)
        return None if index is None else getattr(self._bars[index], field)

    def indicator(self, ref: IndicatorRef, offset: int) -> Decimal | None:
        key = operand_key(ref)
        series = self._indicators.get(key)
        if series is None:
            raise MissingContextValueError(f"no computed series for indicator {key}")
        index = self._index(offset)
        return None if index is None else series[index]
