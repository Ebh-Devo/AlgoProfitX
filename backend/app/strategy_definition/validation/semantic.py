"""Layer 2 (spec §12): does the definition make sense, independent of any environment?

Pure functions over an already-typed ``StrategyDefinition`` and the indicator catalog. This
never parses raw JSON (that is the loader) and never evaluates a condition (that is the
evaluator). Issues are returned in definition order, so the result is deterministic.
"""

from decimal import Decimal
from typing import Any

from app.strategy_definition.errors import ValidationIssue
from app.strategy_definition.indicators import (
    DEFAULT_CATALOG,
    IndicatorCatalog,
    UnknownIndicatorError,
    UnknownIndicatorVersionError,
)
from app.strategy_definition.indicators.spec import SOURCE_UNIT
from app.strategy_definition.loader import MAX_DEPTH
from app.strategy_definition.schema import (
    AllCondition,
    AnyCondition,
    CompareCondition,
    ConstantOperand,
    CrossCondition,
    EdgeCondition,
    IndicatorRef,
    NotCondition,
    PriceOperand,
    StrategyDefinition,
)
from app.strategy_definition.timeframe import is_intraday, timeframe_minutes

_PRICE_FIELDS = ("open", "high", "low", "close")
_COMPARE_OPS = ("gt", "gte", "lt", "lte", "eq")
_UNIT_PRICE = "price"
_UNIT_VOLUME = "volume"


def validate_semantics(
    definition: StrategyDefinition, *, catalog: IndicatorCatalog = DEFAULT_CATALOG
) -> tuple[ValidationIssue, ...]:
    """Every Layer 2 issue in ``definition``; empty when it is semantically sound."""
    return tuple(_Semantics(definition, catalog).run())


class _Semantics:
    def __init__(self, definition: StrategyDefinition, catalog: IndicatorCatalog) -> None:
        self.definition = definition
        self.catalog = catalog
        self.issues: list[ValidationIssue] = []

    def error(self, path: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(path, code, message))

    def run(self) -> list[ValidationIssue]:
        definition = self.definition
        if timeframe_minutes(definition.timeframe) is None:
            self.error("timeframe", "invalid_timeframe", "must look like 5m, 1h, 1d or 1w")
        if definition.evaluation != "bar_close":
            self.error("evaluation", "unsupported_evaluation", "only bar_close is supported")
        for index, rule in enumerate(definition.rules):
            self.condition(rule.when, f"rules[{index}].when", 0)
        return self.issues

    # --- Conditions ---------------------------------------------------------------------

    def condition(self, node: Any, path: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            self.error(path, "max_depth_exceeded", f"nesting deeper than {MAX_DEPTH}")
            return
        if isinstance(node, (AllCondition, AnyCondition)):
            if not node.of:
                self.error(f"{path}.of", "invalid_condition", "must be a non-empty list")
            for index, child in enumerate(node.of):
                self.condition(child, f"{path}.of[{index}]", depth + 1)
        elif isinstance(node, (NotCondition, EdgeCondition)):
            self.condition(node.of, f"{path}.of", depth + 1)
        elif isinstance(node, CompareCondition):
            self.compare(node, path, depth)
        elif isinstance(node, CrossCondition):
            self.cross(node, path, depth)
        else:
            self.error(path, "unsupported_kind", f"unsupported condition {type(node).__name__}")

    def compare(self, node: CompareCondition, path: str, depth: int) -> None:
        if node.op not in _COMPARE_OPS:
            self.error(f"{path}.op", "invalid_condition", f"unknown compare op {node.op!r}")
        sides_ok = self.sides(node, path, depth)
        if node.op == "eq" and (_is_series(node.left) or _is_series(node.right)):
            # Exact equality on price/indicator series is a decimal-equality trap (§8.2).
            self.error(f"{path}.op", "invalid_condition", "eq is not allowed on price or indicator series")
        if sides_ok:
            self.compatible(node, path)

    def cross(self, node: CrossCondition, path: str, depth: int) -> None:
        if node.dir not in ("above", "below"):
            self.error(f"{path}.dir", "invalid_condition", f"unknown cross dir {node.dir!r}")
        sides_ok = self.sides(node, path, depth)
        if not (_is_series(node.left) or _is_series(node.right)):
            # A crossing needs a series to move: two constants never cross.
            self.error(path, "invalid_condition", "cross needs at least one price or indicator series")
        elif sides_ok:
            self.compatible(node, path)

    def sides(self, node: CompareCondition | CrossCondition, path: str, depth: int) -> bool:
        before = len(self.issues)
        self.operand(node.left, f"{path}.left", depth + 1, None, ())
        self.operand(node.right, f"{path}.right", depth + 1, None, ())
        return len(self.issues) == before

    def compatible(self, node: CompareCondition | CrossCondition, path: str) -> None:
        left, right = self.unit(node.left), self.unit(node.right)
        if left is not None and right is not None and left != right:
            self.error(
                path,
                "incompatible_operands",
                f"cannot relate a {left} operand to a {right} operand",
            )

    # --- Operands -----------------------------------------------------------------------

    def operand(
        self,
        node: Any,
        path: str,
        depth: int,
        parent_minutes: int | None,
        chain: tuple[int, ...],
    ) -> None:
        if depth > MAX_DEPTH:
            self.error(path, "max_depth_exceeded", f"nesting deeper than {MAX_DEPTH}")
        elif isinstance(node, PriceOperand):
            if node.field != "volume" and node.field not in _PRICE_FIELDS:
                self.error(f"{path}.field", "invalid_value", f"unknown price field {node.field!r}")
        elif isinstance(node, ConstantOperand):
            if not isinstance(node.value, Decimal) or not node.value.is_finite():
                self.error(f"{path}.value", "invalid_number", "must be a finite number")
        elif isinstance(node, IndicatorRef):
            self.indicator(node, path, depth, parent_minutes, chain)
        else:
            # position / arith and any other reserved operand concept stay rejected.
            self.error(path, "unsupported_kind", f"unsupported operand {type(node).__name__}")

    def indicator(
        self,
        ref: IndicatorRef,
        path: str,
        depth: int,
        parent_minutes: int | None,
        chain: tuple[int, ...],
    ) -> None:
        if id(ref) in chain:
            self.error(path, "indicator_source_cycle", "an indicator cannot be its own source")
            return
        self.catalog_checks(ref, path)
        minutes = self.timeframe(ref, path, parent_minutes)
        if ref.source is not None:
            self.operand(ref.source, f"{path}.source", depth + 1, minutes, chain + (id(ref),))

    def catalog_checks(self, ref: IndicatorRef, path: str) -> None:
        """Pinned name@version, params and output, via the catalog (never re-implemented)."""
        try:
            spec = self.catalog.get(ref.name, ref.version)
        except UnknownIndicatorError as exc:
            self.error(f"{path}.name", "unknown_indicator", str(exc))
            return
        except UnknownIndicatorVersionError as exc:
            self.error(f"{path}.version", "unknown_indicator_version", str(exc))
            return
        for violation in spec.validate_params(ref.params):
            param_path = f"{path}.params"
            if violation.param is not None:
                param_path = f"{param_path}.{violation.param}"
            self.error(param_path, violation.code, violation.message)
        if not spec.has_output(ref.output):
            names = ", ".join(o.name for o in spec.outputs)
            self.error(
                f"{path}.output",
                "unknown_output",
                f"{spec.key} has no output {ref.output!r} (outputs: {names})",
            )
        if spec.anchor == "session" and not is_intraday(ref.timeframe):
            self.error(
                f"{path}.timeframe",
                "session_anchor_requires_intraday",
                f"{spec.key} is session-anchored and needs an intraday timeframe, not {ref.timeframe!r}",
            )

    def timeframe(self, ref: IndicatorRef, path: str, parent_minutes: int | None) -> int | None:
        """Higher-timeframe values are read from completed bars only (§9.3, §17.5), so an
        indicator must sit on a whole multiple of what it is read against: the base timeframe
        at the top level, the consuming indicator's timeframe for a nested source."""
        minutes = timeframe_minutes(ref.timeframe)
        tf_path = f"{path}.timeframe"
        if minutes is None:
            self.error(tf_path, "invalid_timeframe", "must look like 5m, 1h, 1d or 1w")
            return None
        if parent_minutes is None:
            base = timeframe_minutes(self.definition.timeframe)
            if base is None:
                return minutes
            if minutes < base:
                self.error(
                    tf_path,
                    "indicator_timeframe_finer_than_base",
                    f"{ref.timeframe!r} is finer than the definition timeframe {self.definition.timeframe!r}",
                )
            elif minutes % base:
                self.error(
                    tf_path,
                    "indicator_timeframe_misaligned",
                    f"{ref.timeframe!r} is not a multiple of the definition timeframe {self.definition.timeframe!r}",
                )
        elif minutes > parent_minutes or parent_minutes % minutes:
            self.error(
                tf_path,
                "source_timeframe_incompatible",
                f"source timeframe {ref.timeframe!r} must evenly divide the timeframe of the indicator using it",
            )
        return minutes

    # --- Units --------------------------------------------------------------------------

    def unit(self, operand: Any, depth: int = 0) -> str | None:
        """Semantic unit of an operand; ``None`` is a wildcard (constants, unresolvable)."""
        if depth > MAX_DEPTH:
            return None
        if isinstance(operand, PriceOperand):
            return _UNIT_VOLUME if operand.field == "volume" else _UNIT_PRICE
        if isinstance(operand, IndicatorRef):
            try:
                spec = self.catalog.get(operand.name, operand.version)
            except (UnknownIndicatorError, UnknownIndicatorVersionError):
                return None
            unit = next((o.unit for o in spec.outputs if o.name == operand.output), None)
            if unit is None:
                return None
            if unit != SOURCE_UNIT:
                return unit
            return _UNIT_PRICE if operand.source is None else self.unit(operand.source, depth + 1)
        return None


def _is_series(operand: Any) -> bool:
    return isinstance(operand, (PriceOperand, IndicatorRef))
