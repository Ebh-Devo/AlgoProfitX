from dataclasses import replace

from app.strategy_definition.indicators import IndicatorCatalog, IndicatorSpec, OutputSpec, ParamSpec
from app.strategy_definition.indicators.catalog import DEFAULT_CATALOG
from app.strategy_definition.loader import MAX_DEPTH
from app.strategy_definition.schema import (
    AllCondition,
    AnyCondition,
    CompareCondition,
    ConstantOperand,
    CrossCondition,
    EdgeCondition,
    NotCondition,
    PriceOperand,
)
from app.strategy_definition.validation import validate_definition, validate_semantics
from tests.strategy_v2_builders import (
    CLOSE,
    D,
    ema_cross,
    ind,
    leg,
    long_definition,
    position,
    rule,
    op,
    stop,
)
from app.strategy_definition.schema import RiskDefinition


def codes(issues):
    return [(i.path, i.code) for i in issues]


def with_when(when):
    return long_definition(rules=(rule("enter", when, [op("open")]), rule("exit", when, [op("close")])))


def test_valid_long_short_ema_rsi_and_nested_tree():
    assert validate_semantics(long_definition()) == ()
    short = long_definition(positions=(position(legs=[leg(side="sell")]),))
    assert validate_semantics(short) == ()
    rsi = CompareCondition("lt", ind("rsi", 14), ConstantOperand(D(30)))
    assert validate_semantics(with_when(rsi)) == ()
    nested = AllCondition(
        (
            AnyCondition((ema_cross(), NotCondition(rsi))),
            EdgeCondition("rising", CompareCondition("gt", CLOSE, ind("sma", 50))),
        )
    )
    assert validate_semantics(with_when(nested)) == ()


def test_incompatible_operands_in_compare_and_cross():
    price_vs_rsi = CompareCondition("gt", CLOSE, ind("rsi", 14))
    issues = validate_semantics(with_when(price_vs_rsi))
    assert ("rules[0].when", "incompatible_operands") in codes(issues)
    volume_cross = CrossCondition("above", PriceOperand("volume"), CLOSE)
    assert ("rules[0].when", "incompatible_operands") in codes(validate_semantics(with_when(volume_cross)))
    # ema inherits its source's unit, so ema(volume) vs volume is fine; ema(volume) vs close is not.
    ema_volume = ind("ema", 5, source=PriceOperand("volume"))
    assert validate_semantics(with_when(CompareCondition("gt", ema_volume, PriceOperand("volume")))) == ()
    assert codes(validate_semantics(with_when(CompareCondition("gt", ema_volume, CLOSE))))


def test_cross_and_eq_rules():
    two_constants = CrossCondition("above", ConstantOperand(D(1)), ConstantOperand(D(2)))
    assert ("rules[0].when", "invalid_condition") in codes(validate_semantics(with_when(two_constants)))
    eq_series = CompareCondition("eq", CLOSE, ConstantOperand(D(1)))
    assert ("rules[0].when.op", "invalid_condition") in codes(validate_semantics(with_when(eq_series)))
    eq_const = CompareCondition("eq", ConstantOperand(D(1)), ConstantOperand(D(1)))
    assert validate_semantics(with_when(eq_const)) == ()
    assert codes(validate_semantics(with_when(AllCondition(())))) == [("rules[0].when.of", "invalid_condition")] * 1 + [
        ("rules[1].when.of", "invalid_condition")
    ]
    bad_dir = CrossCondition("sideways", CLOSE, ind())
    assert ("rules[0].when.dir", "invalid_condition") in codes(validate_semantics(with_when(bad_dir)))


def test_reserved_operand_concepts_stay_rejected():
    class PositionOperand:  # a future operand kind the schema does not define yet
        pass

    cond = CompareCondition("gt", PositionOperand(), CLOSE)
    assert ("rules[0].when.left", "unsupported_kind") in codes(validate_semantics(with_when(cond)))
    assert ("rules[0].when", "unsupported_kind") in codes(validate_semantics(with_when("nope")))


def test_timeframe_relationships():
    def tf(base, indicator_tf):
        cond = CompareCondition("gt", CLOSE, ind("ema", 9, timeframe=indicator_tf))
        return codes(validate_semantics(replace(with_when(cond), timeframe=base)))

    assert tf("1h", "1d") == []  # higher timeframe, completed bars only
    assert tf("1d", "1d") == []
    assert ("rules[0].when.right.timeframe", "indicator_timeframe_finer_than_base") in tf("1d", "1h")
    assert ("rules[0].when.right.timeframe", "indicator_timeframe_misaligned") in tf("2h", "3h")
    assert ("timeframe", "invalid_timeframe") in tf("daily", "1d")
    assert ("rules[0].when.right.timeframe", "invalid_timeframe") in tf("1d", "x")


def test_nested_source_timeframes_and_depth():
    # EMA(RSI(14, 1h), 9, 1d): the 1h source evenly divides the 1d consumer.
    ok = ind("ema", 9, "1d", source=ind("rsi", 14, "1h"))
    assert validate_semantics(replace(with_when(CompareCondition("gt", ok, ind("ema", 3, "1d", source=ind("rsi", 14, "1h")))), timeframe="1h")) == ()
    bad = ind("ema", 9, "1h", source=ind("rsi", 14, "1d"))
    cond = CompareCondition("gt", bad, ind("ema", 3, "1h", source=ind("rsi", 14, "1d")))
    result = codes(validate_semantics(replace(with_when(cond), timeframe="1h")))
    assert ("rules[0].when.left.source.timeframe", "source_timeframe_incompatible") in result

    deep = CLOSE
    for _ in range(MAX_DEPTH + 2):
        deep = ind("ema", 2, source=deep)
    deep_result = codes(validate_semantics(with_when(CompareCondition("gt", deep, CLOSE))))
    assert any(code == "max_depth_exceeded" for _, code in deep_result)
    nested_cond = CompareCondition("gt", CLOSE, CLOSE)
    for _ in range(MAX_DEPTH + 2):
        nested_cond = NotCondition(nested_cond)
    assert any(c == "max_depth_exceeded" for _, c in codes(validate_semantics(with_when(nested_cond))))


def test_indicator_source_cycle_is_rejected():
    ref = ind("ema", 9)
    object.__setattr__(ref, "source", ref)  # only reachable by bypassing frozen dataclass
    result = codes(validate_semantics(with_when(CompareCondition("gt", ref, CLOSE))))
    assert ("rules[0].when.left.source", "indicator_source_cycle") in result


def test_indicator_catalog_semantics_and_version_pinning():
    unknown = CompareCondition("gt", ind("macd"), CLOSE)
    assert ("rules[0].when.left.name", "unknown_indicator") in codes(validate_semantics(with_when(unknown)))
    pinned = CompareCondition("gt", ind("ema", version=2), CLOSE)
    assert ("rules[0].when.left.version", "unknown_indicator_version") in codes(validate_semantics(with_when(pinned)))
    bad_period = CompareCondition("gt", ind("ema", period=0), CLOSE)
    assert ("rules[0].when.left.params.period", "param_out_of_range") in codes(validate_semantics(with_when(bad_period)))
    bad_output = CompareCondition("gt", ind("ema", output="upper"), CLOSE)
    assert ("rules[0].when.left.output", "unknown_output") in codes(validate_semantics(with_when(bad_output)))


def test_session_anchored_indicator_rejects_daily_timeframe():
    value = (OutputSpec("value", unit="price"),)
    catalog = IndicatorCatalog(
        [*DEFAULT_CATALOG.all(), IndicatorSpec("anchored", 1, (ParamSpec("period", "integer"),), value, anchor="session")]
    )

    def check(timeframe):
        cond = CompareCondition("gt", CLOSE, ind("anchored", 5, timeframe))
        return codes(validate_semantics(replace(with_when(cond), timeframe="5m"), catalog=catalog))

    assert ("rules[0].when.right.timeframe", "session_anchor_requires_intraday") in check("1d")
    assert check("5m") == []


def test_invalid_risk_basis_is_reported_by_full_validation():
    risky = position(risk=RiskDefinition(stop_loss=stop(leg_id="ghost")))
    issues = validate_definition(long_definition(positions=(risky,)))
    assert ("positions.main.risk.stop_loss.basis.leg", "unknown_reference") in codes(issues)


def test_issue_ordering_is_deterministic():
    cond = AllCondition((CompareCondition("eq", CLOSE, ind("rsi", 0)), CompareCondition("gt", CLOSE, ind("rsi", 14))))
    definition = replace(with_when(cond), timeframe="bad")
    first = validate_semantics(definition)
    assert first == validate_semantics(definition)
    paths = [issue.path for issue in first]
    assert paths[0] == "timeframe"
    assert paths.index("rules[0].when.of[0].right.params.period") < paths.index("rules[0].when.of[1]")
    assert all(issue.severity == "error" for issue in first)
