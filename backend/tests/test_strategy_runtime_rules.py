"""Rule engine, conflict resolution and the position state machine."""

from decimal import Decimal

import pytest

from app.strategy_definition.evaluator import Tri, operand_key
from app.strategy_definition.runtime.conflicts import resolve_conflicts
from app.strategy_definition.runtime.errors import UnsupportedOperationError
from app.strategy_definition.runtime.operations import CandidateOperation, OperationSource
from app.strategy_definition.runtime.rules import RuleEngine
from app.strategy_definition.runtime.runtime import StrategyRuntime
from app.strategy_definition.runtime.state import (
    LegSnapshot,
    PositionSnapshot,
    PositionStatus,
    RuntimeSnapshot,
)
from app.strategy_definition.runtime.state_machine import derive_status, precondition_violation
from app.strategy_definition.schema import CompareCondition, ConstantOperand, RuleLimits
from tests.strategy_v2_builders import CLOSE, D, ind, long_definition, op, position, rule
from tests.strategy_v2_runtime_support import context, environment, exec_bar

ABOVE_50 = CompareCondition("gt", CLOSE, ConstantOperand(D(50)))
BELOW_50 = CompareCondition("lt", CLOSE, ConstantOperand(D(50)))


def snapshot(status: PositionStatus = PositionStatus.FLAT, held: str = "0") -> RuntimeSnapshot:
    quantity = Decimal(held)
    leg = LegSnapshot("stock", quantity, Decimal(100) if quantity else None)
    return RuntimeSnapshot((PositionSnapshot("main", status, (leg,)),))


def definition(*rules):
    return long_definition(rules=tuple(rules))


def fired(rules, status=PositionStatus.FLAT, closes=(100,)):
    engine = RuleEngine(definition(*rules))
    return engine.evaluate(context(list(closes), len(closes) - 1), snapshot(status))


# --- Firing ------------------------------------------------------------------------------


def test_true_fires():
    evaluation = fired([rule("r", ABOVE_50, [op("open")])])
    assert [r.result for r in evaluation.results] == [Tri.TRUE]
    assert [c.source.id for c in evaluation.candidates] == ["r"]


def test_false_does_not_fire():
    evaluation = fired([rule("r", BELOW_50, [op("open")])])
    assert [r.result for r in evaluation.results] == [Tri.FALSE]
    assert evaluation.candidates == () and evaluation.skipped == ()


def test_unknown_does_not_fire_and_is_not_false():
    warming = ind("ema", 3)
    series = {operand_key(warming): [None]}
    when = CompareCondition("gt", warming, ConstantOperand(D(1)))
    engine = RuleEngine(definition(rule("r", when, [op("open")])))
    evaluation = engine.evaluate(context([100], 0, series), snapshot())
    assert [r.result for r in evaluation.results] == [Tri.UNKNOWN]
    assert evaluation.candidates == ()


# --- Ordering ----------------------------------------------------------------------------


def test_priority_orders_rules_lower_first():
    engine = RuleEngine(
        definition(
            rule("late", ABOVE_50, [op("open")], priority=10),
            rule("early", ABOVE_50, [op("open")], priority=1),
        )
    )
    assert engine.rule_order == ("early", "late")


def test_declaration_order_breaks_priority_ties_and_unset_ties_together():
    engine = RuleEngine(
        definition(
            rule("a", ABOVE_50, [op("open")]),
            rule("b", ABOVE_50, [op("open")], priority=0),
            rule("c", ABOVE_50, [op("open")]),
            rule("first", ABOVE_50, [op("open")], priority=-1),
        )
    )
    assert engine.rule_order == ("first", "a", "b", "c")


def test_equal_rank_collapses_to_the_first_in_evaluation_order():
    evaluation = fired(
        [
            rule("declared_first", ABOVE_50, [op("open")], priority=5),
            rule("higher_priority", ABOVE_50, [op("open")], priority=1),
        ]
    )
    resolution = resolve_conflicts(evaluation.candidates)
    assert [c.source.id for c in resolution.accepted] == ["higher_priority"]
    assert [(d.candidate.source.id, d.reason) for d in resolution.dropped] == [
        ("declared_first", "equal_rank_duplicate")
    ]


# --- Pre-bar snapshot --------------------------------------------------------------------


def test_rules_never_see_a_same_bar_mutation():
    # r1 opens on this bar. r2 is guarded on "main is open"; it must not fire on the same
    # bar, because every rule reads the immutable pre-bar (flat) snapshot.
    defn = definition(
        rule("r1", ABOVE_50, [op("open")]),
        rule("r2", ABOVE_50, [op("close")], when_position={"main": "open"}),
    )
    closes = [100]
    runtime = StrategyRuntime(defn, environment())
    outcome = runtime.on_bar_close(context(closes, 0), exec_bar(closes, 0))
    assert [(r.rule_id, r.result) for r in outcome.results] == [("r1", Tri.TRUE), ("r2", None)]
    assert [i.op for i in outcome.intents] == ["open"]
    assert runtime.ledger.status("main") is PositionStatus.OPEN
    # Next bar the position is open, so the guarded rule now fires.
    closes = [100, 101]
    outcome = runtime.on_bar_close(context(closes, 1), exec_bar(closes, 1))
    assert [i.op for i in outcome.intents] == ["close"]
    assert runtime.ledger.status("main") is PositionStatus.FLAT


def test_open_and_close_firing_together_on_an_open_position_closes():
    evaluation = fired(
        [rule("o", ABOVE_50, [op("open")]), rule("c", ABOVE_50, [op("close")])],
        status=PositionStatus.OPEN,
        closes=(100,),
    )
    assert [(s.operation.op, s.reason) for s in evaluation.skipped] == [("open", "already_open")]
    resolution = resolve_conflicts(evaluation.candidates)
    assert [c.operation.op for c in resolution.accepted] == ["close"]


# --- Conflicts ---------------------------------------------------------------------------


def _candidate(order, op_name, source="r", position_id="main"):
    return CandidateOperation(OperationSource("rule", source), 0, op(op_name, position_id), order)


def test_close_beats_open_and_later_operations_are_dropped():
    open_first, close_second, open_third = (
        _candidate(0, "open", "a"), _candidate(1, "close", "b"), _candidate(2, "open", "c"),
    )
    resolution = resolve_conflicts([open_first, close_second, open_third])
    assert resolution.accepted == (close_second,)
    assert [(d.candidate.source.id, d.reason) for d in resolution.dropped] == [
        ("a", "after_close"), ("c", "after_close"),
    ]


def test_conflicts_are_per_position_and_deterministic():
    candidates = [
        _candidate(0, "open", "a", "p1"), _candidate(1, "close", "b", "p2"),
        _candidate(2, "open", "c", "p2"), _candidate(3, "open", "d", "p1"),
    ]
    first = resolve_conflicts(candidates)
    assert [(c.position_id, c.source.id) for c in first.accepted] == [("p1", "a"), ("p2", "b")]
    assert resolve_conflicts(list(reversed(candidates))) == first  # input order is irrelevant


def test_rank_is_extensible_to_the_full_order():
    pool = [_candidate(i, name) for i, name in enumerate(["close", "reduce", "increase", "open"])]
    assert resolve_conflicts(pool).accepted[0].operation.op == "close"
    pool = [_candidate(i, name) for i, name in enumerate(["open", "increase", "reduce", "close"])]
    assert resolve_conflicts(pool).accepted[0].operation.op == "close"
    pool = [_candidate(0, "open"), _candidate(1, "increase")]
    assert resolve_conflicts(pool).accepted[0].operation.op == "increase"
    pool = [_candidate(0, "increase"), _candidate(1, "reduce")]
    assert resolve_conflicts(pool).accepted[0].operation.op == "reduce"


# --- State machine -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("held", "working", "expected"),
    [
        ("0", set(), PositionStatus.FLAT),
        ("0", {"open"}, PositionStatus.OPENING),
        ("10", set(), PositionStatus.OPEN),
        ("10", {"close"}, PositionStatus.CLOSING),
        ("4", {"open"}, PositionStatus.OPENING),
    ],
)
def test_status_is_derived_from_held_quantity_and_working_orders(held, working, expected):
    assert derive_status({"s": Decimal(held)}, {"s": Decimal(1)}, working) is expected


def test_incomplete_leg_set_is_degraded():
    ratios = {"call": Decimal(1), "put": Decimal(1)}
    assert derive_status({"call": D(10), "put": D(0)}, ratios, set()) is PositionStatus.DEGRADED
    assert derive_status({"call": D(10), "put": D(-10)}, ratios, set()) is PositionStatus.OPEN


@pytest.mark.parametrize(
    ("status", "op_name", "reason"),
    [
        (PositionStatus.FLAT, "open", None),
        (PositionStatus.OPEN, "open", "already_open"),
        (PositionStatus.OPENING, "open", "already_opening"),
        (PositionStatus.CLOSING, "open", "already_closing"),
        (PositionStatus.DEGRADED, "open", "degraded"),
        (PositionStatus.OPEN, "close", None),
        (PositionStatus.DEGRADED, "close", None),
        (PositionStatus.FLAT, "close", "flat"),
        (PositionStatus.OPENING, "close", "already_opening"),
        (PositionStatus.CLOSING, "close", "already_closing"),
    ],
)
def test_operation_preconditions(status, op_name, reason):
    assert precondition_violation(status, op_name) == reason


# --- Reserved features are refused, never ignored ---------------------------------------


@pytest.mark.parametrize("name", ["increase", "reduce"])
def test_increase_and_reduce_are_reserved(name):
    with pytest.raises(UnsupportedOperationError):
        RuleEngine(definition(rule("r", ABOVE_50, [op(name)])))


def test_rule_limits_are_refused_rather_than_ignored():
    with pytest.raises(UnsupportedOperationError):
        RuleEngine(definition(rule("r", ABOVE_50, [op("open")], limits=RuleLimits(1))))


def test_position_snapshot_is_immutable():
    snap = snapshot()
    with pytest.raises(AttributeError):
        snap.positions[0].status = PositionStatus.OPEN  # type: ignore[misc]
    assert position().id == "main"
