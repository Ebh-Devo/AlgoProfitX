"""Pure condition evaluator (docs/STRATEGY_DEFINITION_V2.md §8).

Answers one question: given a condition and the values available at bar ``t``, is it
TRUE, FALSE or UNKNOWN? It computes no indicators and keeps no state.
"""

from decimal import Decimal

from app.strategy_definition.evaluator.context import EvaluationContext, check_decimal, check_offset
from app.strategy_definition.evaluator.errors import UnsupportedConstructError
from app.strategy_definition.evaluator.result import Tri, tri_all, tri_any, tri_not
from app.strategy_definition.schema import (
    AllCondition,
    AnyCondition,
    CompareCondition,
    Condition,
    ConstantOperand,
    CrossCondition,
    EdgeCondition,
    IndicatorRef,
    NotCondition,
    Operand,
    PriceOperand,
)


def evaluate_condition(condition: Condition, context: EvaluationContext) -> Tri:
    """Evaluate ``condition`` at the context's current bar."""
    return _evaluate(condition, context, 0)


def _evaluate(condition: Condition, context: EvaluationContext, offset: int) -> Tri:
    check_offset(offset)
    if isinstance(condition, AllCondition):
        return tri_all([_evaluate(child, context, offset) for child in condition.of])
    if isinstance(condition, AnyCondition):
        return tri_any([_evaluate(child, context, offset) for child in condition.of])
    if isinstance(condition, NotCondition):
        return tri_not(_evaluate(condition.of, context, offset))
    if isinstance(condition, CompareCondition):
        return _compare(condition, context, offset)
    if isinstance(condition, CrossCondition):
        return _cross(condition, context, offset)
    if isinstance(condition, EdgeCondition):
        if condition.dir != "rising":
            raise UnsupportedConstructError(f"unsupported edge dir {condition.dir!r}")
        current = _evaluate(condition.of, context, offset)
        previous = _evaluate(condition.of, context, offset - 1)
        return tri_all([current, tri_not(previous)])
    raise UnsupportedConstructError(
        f"unsupported condition {getattr(condition, 'kind', type(condition).__name__)!r}"
    )


def _is_series(operand: Operand) -> bool:
    return isinstance(operand, (PriceOperand, IndicatorRef))


def _value(operand: Operand, context: EvaluationContext, offset: int) -> Decimal | None:
    if isinstance(operand, ConstantOperand):
        return check_decimal(operand.value)
    if isinstance(operand, PriceOperand):
        return check_decimal(context.price(operand.field, offset))
    if isinstance(operand, IndicatorRef):
        return check_decimal(context.indicator(operand, offset))
    raise UnsupportedConstructError(
        f"unsupported operand {getattr(operand, 'kind', type(operand).__name__)!r}"
    )


def _compare(condition: CompareCondition, context: EvaluationContext, offset: int) -> Tri:
    op = condition.op
    if op not in ("gt", "gte", "lt", "lte", "eq"):
        raise UnsupportedConstructError(f"unsupported compare op {op!r}")
    if op == "eq" and (_is_series(condition.left) or _is_series(condition.right)):
        raise UnsupportedConstructError("eq is not allowed on price or indicator series")
    left = _value(condition.left, context, offset)
    right = _value(condition.right, context, offset)
    if left is None or right is None:
        return Tri.UNKNOWN
    if op == "gt":
        result = left > right
    elif op == "gte":
        result = left >= right
    elif op == "lt":
        result = left < right
    elif op == "lte":
        result = left <= right
    else:
        result = left == right
    return Tri.TRUE if result else Tri.FALSE


def _cross(condition: CrossCondition, context: EvaluationContext, offset: int) -> Tri:
    if condition.dir not in ("above", "below"):
        raise UnsupportedConstructError(f"unsupported cross dir {condition.dir!r}")
    left_now = _value(condition.left, context, offset)
    right_now = _value(condition.right, context, offset)
    left_prev = _value(condition.left, context, offset - 1)
    right_prev = _value(condition.right, context, offset - 1)
    if left_now is None or right_now is None or left_prev is None or right_prev is None:
        return Tri.UNKNOWN
    if condition.dir == "above":
        result = left_prev <= right_prev and left_now > right_now
    else:
        result = left_prev >= right_prev and left_now < right_now
    return Tri.TRUE if result else Tri.FALSE
