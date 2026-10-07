from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import product

import pytest

from app.strategy_definition.evaluator import (
    Bar,
    HistoricalContext,
    InvalidEvaluationRequestError,
    MissingContextValueError,
    Tri,
    UnsupportedConstructError,
    evaluate_condition,
    operand_key,
)
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
)

D = Decimal
T, F, U = Tri.TRUE, Tri.FALSE, Tri.UNKNOWN
START = datetime(2024, 1, 1, tzinfo=timezone.utc)


def ind(name: str, period: int) -> IndicatorRef:
    return IndicatorRef(
        name=name,
        version=1,
        params={"period": period},
        source=PriceOperand("close"),
        timeframe="1d",
        output="value",
    )


FAST, SLOW, RSI = ind("ema", 9), ind("ema", 21), ind("rsi", 14)
CLOSE = PriceOperand("close")


def const(value: str) -> ConstantOperand:
    return ConstantOperand(D(value))


def dec(values):
    return [None if v is None else D(str(v)) for v in values]


def ctx(closes=(), series=None, volumes=None) -> HistoricalContext:
    """Context whose current bar is the last element. ``series`` maps fast/slow/rsi -> values."""
    closes = dec(closes)
    volumes = dec(volumes) if volumes is not None else [None] * len(closes)
    bars = [
        Bar(START + timedelta(days=i), c, c, c, c, v)
        for i, (c, v) in enumerate(zip(closes, volumes))
    ]
    refs = {"fast": FAST, "slow": SLOW, "rsi": RSI}
    indicators = {operand_key(refs[name]): dec(vals) for name, vals in (series or {}).items()}
    return HistoricalContext(bars, indicators)


def two_bar(left_prev, left_now, right_prev, right_now) -> HistoricalContext:
    return ctx(
        [1, 1], {"fast": [left_prev, left_now], "slow": [right_prev, right_now]}
    )


def cond_const(value: Tri):
    """A condition that deterministically evaluates to ``value`` (no context needed)."""
    if value is T:
        return CompareCondition("gt", const("1"), const("0"))
    if value is F:
        return CompareCondition("gt", const("0"), const("1"))
    return CompareCondition("gt", CLOSE, const("0"))  # close undefined -> UNKNOWN


UNDEFINED = ctx([None])


# --- three-valued logic -----------------------------------------------------------------


def test_cond_const_helper():
    for value in Tri:
        assert evaluate_condition(cond_const(value), UNDEFINED if value is U else ctx([1])) is value


@pytest.mark.parametrize("n", [1, 2, 3])
def test_all_truth_table(n):
    for combo in product(Tri, repeat=n):
        expected = F if F in combo else U if U in combo else T
        node = AllCondition(tuple(cond_const(v) for v in combo))
        # F/T constants do not read the context, so one shared context serves every combo
        assert evaluate_condition(node, UNDEFINED) is expected, combo


@pytest.mark.parametrize("n", [1, 2, 3])
def test_any_truth_table(n):
    for combo in product(Tri, repeat=n):
        expected = T if T in combo else U if U in combo else F
        node = AnyCondition(tuple(cond_const(v) for v in combo))
        assert evaluate_condition(node, UNDEFINED) is expected, combo


def test_not_truth_table():
    for value, expected in ((T, F), (F, T), (U, U)):
        assert evaluate_condition(NotCondition(cond_const(value)), ctx([None])) is expected


def test_only_true_fires():
    assert T.fires and not F.fires and not U.fires


# --- compare ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "op,left,right,expected",
    [
        ("gt", "2", "1", T),
        ("gt", "1", "2", F),
        ("gt", "1", "1", F),
        ("gte", "2", "1", T),
        ("gte", "1", "1", T),
        ("gte", "1", "2", F),
        ("lt", "1", "2", T),
        ("lt", "2", "1", F),
        ("lt", "1", "1", F),
        ("lte", "1", "2", T),
        ("lte", "1", "1", T),
        ("lte", "2", "1", F),
        ("eq", "1", "1", T),
        ("eq", "1.0", "1.00", T),
        ("eq", "1", "2", F),
    ],
)
def test_compare_constants(op, left, right, expected):
    assert evaluate_condition(CompareCondition(op, const(left), const(right)), ctx([1])) is expected


def test_compare_decimal_precision_boundaries():
    context = ctx(["100.10", "100.1000000001"])
    assert evaluate_condition(CompareCondition("gt", CLOSE, const("100.1")), context) is T
    assert evaluate_condition(CompareCondition("gte", CLOSE, const("100.1000000001")), context) is T
    assert evaluate_condition(CompareCondition("lt", CLOSE, const("100.1000000002")), context) is T
    assert evaluate_condition(CompareCondition("lte", CLOSE, const("100.1000000000")), context) is F


def test_compare_reads_indicator_and_price_at_current_bar():
    context = ctx([10, 20], {"rsi": [30, 55]})
    assert evaluate_condition(CompareCondition("gt", RSI, const("50")), context) is T
    assert evaluate_condition(CompareCondition("lt", CLOSE, const("15")), context) is F


@pytest.mark.parametrize("op", ["gt", "gte", "lt", "lte"])
def test_compare_undefined_operand_is_unknown(op):
    context = ctx([1, 2], {"rsi": [None, None]})
    assert evaluate_condition(CompareCondition(op, RSI, const("50")), context) is U
    assert evaluate_condition(CompareCondition(op, const("50"), RSI), context) is U


def test_compare_missing_volume_is_unknown():
    assert evaluate_condition(
        CompareCondition("gt", PriceOperand("volume"), const("0")), ctx([1])
    ) is U


def test_eq_on_series_is_rejected_not_approximated():
    context = ctx([1], {"rsi": [50]})
    with pytest.raises(UnsupportedConstructError):
        evaluate_condition(CompareCondition("eq", RSI, const("50")), context)
    with pytest.raises(UnsupportedConstructError):
        evaluate_condition(CompareCondition("eq", CLOSE, const("1")), context)


# --- cross ------------------------------------------------------------------------------


def cross(direction):
    return CrossCondition(direction, FAST, SLOW)


def test_cross_above_exact():
    assert evaluate_condition(cross("above"), two_bar(9, 11, 10, 10)) is T


def test_cross_above_none():
    assert evaluate_condition(cross("above"), two_bar(11, 12, 10, 10)) is F  # already above
    assert evaluate_condition(cross("above"), two_bar(8, 9, 10, 10)) is F  # still below
    assert evaluate_condition(cross("above"), two_bar(11, 9, 10, 10)) is F  # opposite direction


def test_cross_above_equal_previous_counts():
    assert evaluate_condition(cross("above"), two_bar(10, 11, 10, 10)) is T  # <= then >


def test_cross_above_equal_current_does_not_cross():
    assert evaluate_condition(cross("above"), two_bar(9, 10, 10, 10)) is F  # needs strict >


def test_cross_above_previous_above_is_not_a_cross():
    assert evaluate_condition(cross("above"), two_bar(10.01, 11, 10, 10)) is F


def test_cross_below_exact():
    assert evaluate_condition(cross("below"), two_bar(11, 9, 10, 10)) is T


def test_cross_below_none():
    assert evaluate_condition(cross("below"), two_bar(9, 8, 10, 10)) is F
    assert evaluate_condition(cross("below"), two_bar(11, 12, 10, 10)) is F
    assert evaluate_condition(cross("below"), two_bar(9, 11, 10, 10)) is F


def test_cross_below_equal_previous_counts():
    assert evaluate_condition(cross("below"), two_bar(10, 9, 10, 10)) is T  # >= then <


def test_cross_below_equal_current_does_not_cross():
    assert evaluate_condition(cross("below"), two_bar(11, 10, 10, 10)) is F


@pytest.mark.parametrize("direction", ["above", "below"])
@pytest.mark.parametrize(
    "values",
    [
        (None, 11, 10, 10),
        (9, None, 10, 10),
        (9, 11, None, 10),
        (9, 11, 10, None),
    ],
)
def test_cross_undefined_value_is_unknown(direction, values):
    assert evaluate_condition(cross(direction), two_bar(*values)) is U


def test_cross_on_first_bar_has_no_previous_so_unknown():
    context = ctx([1], {"fast": [11], "slow": [10]})
    assert evaluate_condition(cross("above"), context) is U


def test_cross_against_constant_and_price():
    context = ctx([49, 51], {"rsi": [49, 51]})
    assert evaluate_condition(CrossCondition("above", RSI, const("50")), context) is T
    assert evaluate_condition(CrossCondition("above", CLOSE, const("50")), context) is T
    assert evaluate_condition(CrossCondition("below", CLOSE, const("50")), context) is F


# --- edge -------------------------------------------------------------------------------


def edge_of_gt50(prev, now) -> Tri:
    """Edge over RSI > 50 where RSI is [prev, now]."""
    context = ctx([1, 1], {"rsi": [prev, now]})
    return evaluate_condition(EdgeCondition("rising", CompareCondition("gt", RSI, const("50"))), context)


def test_edge_truth_table():
    assert edge_of_gt50(40, 60) is T  # FALSE -> TRUE
    assert edge_of_gt50(60, 70) is F  # TRUE -> TRUE
    assert edge_of_gt50(60, 40) is F  # TRUE -> FALSE
    assert edge_of_gt50(40, 30) is F  # FALSE -> FALSE


def test_edge_unknown_involvement():
    assert edge_of_gt50(None, 60) is U  # UNKNOWN -> TRUE
    assert edge_of_gt50(40, None) is U  # FALSE -> UNKNOWN
    assert edge_of_gt50(None, 40) is F  # FALSE now -> FALSE regardless of previous
    assert edge_of_gt50(60, None) is F  # TRUE -> UNKNOWN: previous TRUE rules it out
    assert edge_of_gt50(None, None) is U


def test_edge_on_first_bar_is_unknown():
    context = ctx([1], {"rsi": [60]})
    assert evaluate_condition(
        EdgeCondition("rising", CompareCondition("gt", RSI, const("50"))), context
    ) is U


def test_edge_nested_cross_uses_one_further_bar_back():
    # cross above happened on bar 2; edge of a cross child evaluated at t=2 sees cross[2]=T,
    # cross[1]=F -> TRUE; evaluated at t=3 sees cross[3]=F -> FALSE.
    fast, slow = [8, 9, 11, 12], [10, 10, 10, 10]
    edge = EdgeCondition("rising", cross("above"))

    def at(t):
        return ctx(
            [1] * (t + 1), {"fast": fast[: t + 1], "slow": slow[: t + 1]}
        )

    assert evaluate_condition(edge, at(2)) is T
    assert evaluate_condition(edge, at(3)) is F
    assert evaluate_condition(edge, at(1)) is F  # cross[1] is FALSE, so FALSE despite cross[0]
    unknown_prev = ctx([1, 1], {"fast": [8, 11], "slow": [10, 10]})
    assert evaluate_condition(edge, unknown_prev) is U  # cross[1] TRUE, cross[0] undefined


def test_edge_of_boolean_composition():
    node = EdgeCondition(
        "rising",
        AllCondition((CompareCondition("gt", RSI, const("50")), CompareCondition("gt", CLOSE, const("10")))),
    )
    assert evaluate_condition(node, ctx([5, 20], {"rsi": [60, 60]})) is T
    assert evaluate_condition(node, ctx([20, 20], {"rsi": [60, 60]})) is F


# --- nested -----------------------------------------------------------------------------


def test_cross_and_level():
    node = AllCondition((cross("above"), CompareCondition("gt", RSI, const("50"))))
    base = {"fast": [9, 11], "slow": [10, 10]}
    assert evaluate_condition(node, ctx([1, 1], {**base, "rsi": [40, 60]})) is T
    assert evaluate_condition(node, ctx([1, 1], {**base, "rsi": [40, 45]})) is F
    assert evaluate_condition(node, ctx([1, 1], {**base, "rsi": [None, None]})) is U


def test_any_not_edge_combination():
    rsi_hi = CompareCondition("gt", RSI, const("50"))
    node = AnyCondition((NotCondition(rsi_hi), EdgeCondition("rising", cross("above"))))
    base = {"fast": [9, 11], "slow": [10, 10]}
    assert evaluate_condition(node, ctx([1, 1], {**base, "rsi": [60, 60]})) is U  # cross edge: prev UNKNOWN
    assert evaluate_condition(node, ctx([1, 1], {**base, "rsi": [60, 40]})) is T  # not(rsi>50)
    assert evaluate_condition(node, ctx([1, 1], {**base, "rsi": [60, None]})) is U


def test_deeply_nested():
    node = NotCondition(
        AllCondition(
            (
                AnyCondition((cross("above"), cross("below"))),
                NotCondition(CompareCondition("lt", RSI, const("30"))),
            )
        )
    )
    context = ctx([1, 1], {"fast": [9, 11], "slow": [10, 10], "rsi": [50, 50]})
    assert evaluate_condition(node, context) is F


# --- warm-up ----------------------------------------------------------------------------


def test_not_unknown_is_unknown_and_rule_cannot_fire_in_warmup():
    context = ctx([1, 1], {"rsi": [None, None]})
    inner = CompareCondition("lt", RSI, const("30"))
    assert evaluate_condition(inner, context) is U
    result = evaluate_condition(NotCondition(inner), context)
    assert result is U
    assert not result.fires


def test_missing_indicator_is_unknown_not_false():
    context = ctx([1, 1, 1], {"rsi": [None, None, "55"]})
    gt = CompareCondition("gt", RSI, const("50"))
    assert evaluate_condition(gt, ctx([1, 1], {"rsi": [None, None]})) is U
    assert evaluate_condition(gt, context) is T


# --- temporal safety --------------------------------------------------------------------


class SpyContext:
    def __init__(self, inner):
        self.inner = inner
        self.offsets = []

    @property
    def timestamp(self):
        return self.inner.timestamp

    def price(self, field, offset):
        self.offsets.append(offset)
        return self.inner.price(field, offset)

    def indicator(self, ref, offset):
        self.offsets.append(offset)
        return self.inner.indicator(ref, offset)


def test_evaluator_never_requests_positive_offset():
    node = AllCondition(
        (
            EdgeCondition("rising", cross("above")),
            NotCondition(CompareCondition("gt", CLOSE, const("0"))),
            cross("below"),
        )
    )
    spy = SpyContext(ctx([1, 2, 3, 4], {"fast": [1, 2, 3, 4], "slow": [4, 3, 2, 1]}))
    evaluate_condition(node, spy)
    assert spy.offsets and max(spy.offsets) == 0
    assert min(spy.offsets) == -2  # edge over cross reaches back two bars, no further


def test_context_rejects_future_offsets():
    context = ctx([1, 2], {"rsi": [1, 2]})
    with pytest.raises(InvalidEvaluationRequestError):
        context.price("close", 1)
    with pytest.raises(InvalidEvaluationRequestError):
        context.indicator(RSI, 1)


def test_result_at_each_t_uses_only_bars_up_to_t():
    closes = [10, 11, 12, 11, 9, 14, 15]
    fast = [None, 9, 10, 11, 10, 12, 13]
    slow = [None, 10, 10, 10, 10, 11, 12]
    node = AllCondition((cross("above"), CompareCondition("gt", CLOSE, const("10"))))
    results = [
        evaluate_condition(
            node, ctx(closes[: t + 1], {"fast": fast[: t + 1], "slow": slow[: t + 1]})
        )
        for t in range(len(closes))
    ]
    assert results == [F, U, F, T, F, T, F]


# --- errors -----------------------------------------------------------------------------


def test_missing_indicator_series_is_an_error_not_unknown():
    with pytest.raises(MissingContextValueError):
        evaluate_condition(CompareCondition("gt", RSI, const("50")), ctx([1]))


def test_unsupported_condition_kind():
    class Within:
        kind = "within"

    with pytest.raises(UnsupportedConstructError):
        evaluate_condition(Within(), ctx([1]))  # type: ignore[arg-type]


def test_unsupported_operand_kind():
    class Arith:
        kind = "arith"

    with pytest.raises(UnsupportedConstructError):
        evaluate_condition(CompareCondition("gt", Arith(), const("1")), ctx([1]))  # type: ignore[arg-type]


def test_unsupported_compare_op():
    with pytest.raises(UnsupportedConstructError):
        evaluate_condition(CompareCondition("ne", const("1"), const("1")), ctx([1]))  # type: ignore[arg-type]


def test_non_decimal_context_values_rejected():
    bad = Bar(START, 1.0, 1.0, 1.0, 1.0, None)  # type: ignore[arg-type]
    with pytest.raises(InvalidEvaluationRequestError):
        HistoricalContext([bad])


def test_misaligned_indicator_series_rejected():
    with pytest.raises(InvalidEvaluationRequestError):
        ctx([1, 2], {"rsi": [1]})


def test_empty_context_rejected():
    with pytest.raises(InvalidEvaluationRequestError):
        HistoricalContext([])


# --- determinism ------------------------------------------------------------------------


def test_repeated_evaluation_is_identical():
    node = AllCondition(
        (EdgeCondition("rising", cross("above")), NotCondition(CompareCondition("lt", RSI, const("30"))))
    )
    context = ctx([1, 1, 1], {"fast": [8, 9, 11], "slow": [10, 10, 10], "rsi": [50, 50, 50]})
    results = {evaluate_condition(node, context) for _ in range(50)}
    assert len(results) == 1


def test_operand_key_is_canonical():
    same = IndicatorRef("ema", 1, {"period": 9}, PriceOperand("close"), "1d", "value")
    assert operand_key(same) == operand_key(FAST)
    assert operand_key(FAST) != operand_key(SLOW)
