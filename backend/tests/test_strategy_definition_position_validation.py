from dataclasses import replace

import pytest

from app.strategy_definition.schema import (
    Amount,
    InstrumentSelector,
    PercentOfAllocationSizing,
    Quantity,
    RiskDefinition,
    RuleLimits,
    SharesSizing,
)
from app.strategy_definition.validation import validate_position_semantics
from tests.strategy_v2_builders import D, leg, long_definition, op, position, rule, stop


def codes(issues):
    return [(i.path, i.code) for i in issues]


def hedged(**hedge_changes):
    hedge = position("put", "hedge", "main", [leg("put_leg")])
    hedge = replace(hedge, **hedge_changes)
    return long_definition(
        positions=(position(), hedge),
        rules=(
            rule("enter", then=[op("open", "main"), op("open", "put")]),
            rule("exit", then=[op("close", "main"), op("close", "put")]),
        ),
    )


def test_valid_core_and_valid_hedge_and_multiple_rules():
    assert validate_position_semantics(long_definition()) == ()
    assert validate_position_semantics(hedged()) == ()
    scaled = long_definition(
        rules=(
            rule("enter", then=[op("open")]),
            rule("add", then=[op("increase", amount=Amount("sizing_unit", D(1)))]),
            rule("trim", then=[op("reduce", amount=Amount("fraction_of_open", D("0.5")))]),
            rule("exit", then=[op("close")], when_position={"main": "open"}, limits=RuleLimits(1)),
        )
    )
    assert validate_position_semantics(scaled) == ()


def test_hedge_relationships():
    assert ("positions.put.hedges", "unknown_reference") in codes(
        validate_position_semantics(hedged(hedges="ghost"))
    )
    assert ("positions.put.hedges", "invalid_position") in codes(
        validate_position_semantics(hedged(hedges="put"))
    )
    assert ("positions.put.hedges", "invalid_position") in codes(
        validate_position_semantics(hedged(hedges=None))
    )
    core_with_target = long_definition(positions=(position(hedges="main"),))
    assert ("positions.main.hedges", "invalid_position") in codes(validate_position_semantics(core_with_target))


def test_hedge_of_hedge_and_cycles_are_rejected():
    chain = long_definition(
        positions=(
            position(),
            position("h1", "hedge", "main", [leg("l1")]),
            position("h2", "hedge", "h1", [leg("l2")]),
        ),
        rules=(rule("enter", then=[op("open", "main"), op("open", "h1"), op("open", "h2")]),),
    )
    assert ("positions.h2.hedges", "invalid_hedge_target") in codes(validate_position_semantics(chain))
    cycle = long_definition(
        positions=(
            position("a", "hedge", "b", [leg("la")]),
            position("b", "hedge", "a", [leg("lb")]),
        ),
        rules=(rule("enter", then=[op("open", "a"), op("open", "b")]),),
    )
    result = codes(validate_position_semantics(cycle))
    assert ("positions.a.hedges", "invalid_hedge_target") in result
    assert ("positions.b.hedges", "invalid_hedge_target") in result


def test_hedge_lifecycle_warnings():
    only_open = long_definition(
        positions=(position(), position("put", "hedge", "main", [leg("put_leg")])),
        rules=(
            rule("enter", then=[op("open", "main"), op("open", "put")]),
            rule("exit", then=[op("close", "main")]),
        ),
    )
    issues = validate_position_semantics(only_open)
    assert [(i.code, i.severity) for i in issues] == [("hedge_may_outlive_parent", "warning")]
    parent_never = long_definition(
        positions=(position(), position("put", "hedge", "main", [leg("put_leg")])),
        rules=(rule("enter", then=[op("open", "put")]),),
    )
    assert ("hedge_parent_never_opened", "warning") in [(i.code, i.severity) for i in validate_position_semantics(parent_never)]


def test_leg_and_sizing_semantics():
    no_legs = long_definition(positions=(position(legs=[]),))
    assert ("positions.main.legs", "invalid_position") in codes(validate_position_semantics(no_legs))
    dup = long_definition(positions=(position(legs=[leg("a"), leg("a")]),))
    assert ("positions.main.legs[1]", "duplicate_id") in codes(validate_position_semantics(dup))
    zero = long_definition(positions=(position(legs=[replace(leg(), quantity=Quantity(D(0)))]),))
    assert ("positions.main.legs[0].quantity", "invalid_quantity") in codes(validate_position_semantics(zero))
    option = long_definition(positions=(position(legs=[replace(leg(), instrument=InstrumentSelector("option"))]),))
    assert ("positions.main.legs[0].instrument", "unsupported_kind") in codes(validate_position_semantics(option))
    pct = long_definition(positions=(position(sizing=PercentOfAllocationSizing(D(100))),))
    assert ("positions.main.sizing.unit", "sizing_not_authorable") in codes(validate_position_semantics(pct))
    bad_shares = long_definition(positions=(position(sizing=SharesSizing(D(0))),))
    assert ("positions.main.sizing.value", "invalid_quantity") in codes(validate_position_semantics(bad_shares))
    clash = long_definition(positions=(position(legs=[leg("enter")]),))
    assert ("rules[0]", "duplicate_id") in codes(validate_position_semantics(clash))  # shared namespace


@pytest.mark.parametrize("kind", ["close", "reduce", "increase"])
def test_operation_without_possible_open(kind):
    amount = Amount("fraction_of_open", D("0.5")) if kind != "close" else None
    definition = long_definition(rules=(rule("only", then=[op(kind, amount=amount)]),))
    assert codes(validate_position_semantics(definition)) == [
        ("rules[0].then[0].position", "position_never_opened")
    ]


def test_operations_on_undeclared_positions_and_guards():
    definition = long_definition(rules=(rule("r", then=[op("open", "ghost")]),))
    assert codes(validate_position_semantics(definition)) == [("rules[0].then[0].position", "unknown_reference")]
    guard = long_definition(
        positions=(position(), position("other", legs=[leg("other_leg")])),
        rules=(rule("r", then=[op("open")], when_position={"other": "open", "ghost": "flat"}),),
    )
    result = codes(validate_position_semantics(guard))
    assert ("rules[0].when_position.other", "rule_never_fires") in result
    assert ("rules[0].when_position.ghost", "unknown_reference") in result


def test_invalid_operation_amounts():
    def one(operation):
        return codes(validate_position_semantics(long_definition(rules=(rule("a", then=[op()]), rule("b", then=[operation])))))

    path = "rules[1].then[0].amount"
    assert one(op("reduce")) == [(path, "invalid_operation")]
    assert one(op("open", amount=Amount("sizing_unit", D(1)))) == [(path, "invalid_operation")]
    assert one(op("reduce", amount=Amount("fraction_of_open", D("1.5")))) == [(path + ".value", "invalid_amount")]
    assert one(op("increase", amount=Amount("fraction_of_open", D("1.5")))) == []
    assert one(op("increase", amount=Amount("sizing_unit", D(0)))) == [(path + ".value", "invalid_amount")]
    assert one(op("reduce", amount=Amount("lots", D(1)))) == [(path + ".unit", "invalid_value")]


def test_rule_shape_and_conflicts():
    empty = long_definition(rules=(rule("r", then=[]),))
    assert ("rules[0].then", "invalid_rule") in codes(validate_position_semantics(empty))
    both = long_definition(rules=(rule("r", then=[op("open"), op("close")]),))
    assert [(i.code, i.severity) for i in validate_position_semantics(both)] == [("conflicting_operations", "warning")]
    dup = long_definition(rules=(rule("r", then=[op()]), rule("r", then=[op("close")])))
    assert ("rules[1]", "duplicate_id") in codes(validate_position_semantics(dup))
    limits = long_definition(rules=(rule("r", then=[op()], limits=RuleLimits(0)),))
    assert ("rules[0].limits.max_fires_per_position", "invalid_number") in codes(validate_position_semantics(limits))


def test_risk_semantics():
    ok = long_definition(positions=(position(risk=RiskDefinition(stop_loss=stop(), take_profit=stop("5"))),))
    assert validate_position_semantics(ok) == ()
    other_leg = long_definition(positions=(position(risk=RiskDefinition(stop_loss=stop(leg_id="ghost"))),))
    assert codes(validate_position_semantics(other_leg)) == [("positions.main.risk.stop_loss.basis.leg", "unknown_reference")]
    zero = long_definition(positions=(position(risk=RiskDefinition(take_profit=stop("0"))),))
    assert codes(validate_position_semantics(zero)) == [("positions.main.risk.take_profit.value", "invalid_risk")]

    class FuturePnlBasis:
        kind = "position_pnl_pct"

    reserved = replace(stop(), basis=FuturePnlBasis())
    result = validate_position_semantics(long_definition(positions=(position(risk=RiskDefinition(stop_loss=reserved)),)))
    assert codes(result) == [("positions.main.risk.stop_loss.basis", "unsupported_kind")]
    # A leg of a *different* position is not a valid basis for this one.
    two = long_definition(
        positions=(
            position(risk=RiskDefinition(stop_loss=stop(leg_id="side_leg"))),
            position("side", legs=[leg("side_leg")]),
        ),
        rules=(rule("r", then=[op("open"), op("open", "side")]),),
    )
    assert ("positions.main.risk.stop_loss.basis.leg", "unknown_reference") in codes(validate_position_semantics(two))


def test_analysis_is_deterministic_and_pure():
    definition = long_definition(
        positions=(position(), position("main", legs=[leg("stock")])),
        rules=(rule("r", then=[op("close", "main"), op("reduce", "ghost")]),),
    )
    first = validate_position_semantics(definition)
    assert first == validate_position_semantics(definition)
    assert first == tuple(first)
    assert len(first) >= 3
