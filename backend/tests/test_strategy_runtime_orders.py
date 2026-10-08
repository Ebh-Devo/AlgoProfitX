"""Order intents, side derivation, planning, simulated execution and the ledger."""

from dataclasses import fields, replace
from decimal import Decimal

import pytest

from app.strategy_definition.runtime.errors import (
    ExecutionError,
    LedgerInconsistencyError,
    RuntimeDataError,
    UnsupportedOperationError,
)
from app.strategy_definition.runtime.execution import (
    EventType,
    ExecutionBar,
    ExecutionEvent,
    PartialFill,
    Reject,
    SimulatedExecutionAdapter,
)
from app.strategy_definition.runtime.intents import make_group_id, make_intent_id
from app.strategy_definition.runtime.ledger import (
    Ledger,
    LedgerLegSpec,
    LedgerPositionSpec,
    OrderRegistration,
    ledger_specs,
)
from app.strategy_definition.runtime.operations import CandidateOperation, OperationSource
from app.strategy_definition.runtime.planner import (
    OrderPlanner,
    PrimaryInstrumentResolver,
    derive_side,
)
from app.strategy_definition.runtime.state import PositionStatus
from app.strategy_definition.schema import PercentOfAllocationSizing, SharesSizing
from tests.strategy_v2_builders import D, leg, long_definition, op, position
from tests.strategy_v2_runtime_support import intent, ts

RULE = OperationSource("rule", "enter")
SPEC = LedgerPositionSpec("main", (LedgerLegSpec("stock", "buy", D(1)),))


def ledger(capital="10000") -> Ledger:
    return Ledger([SPEC], D(capital))


def ev(intent_id, seq, kind, qty=None, price=None, at=0, **extra) -> ExecutionEvent:
    return ExecutionEvent(
        intent_id, seq, kind, ts(at),
        None if qty is None else D(qty), None if price is None else D(price), **extra,
    )


def fill(book: Ledger, order, price="100", at=0, qty=None):
    quantity = qty or str(order.quantity)
    book.apply_event(ev(order.intent_id, 1, EventType.ACCEPTED, at=at))
    book.apply_event(ev(order.intent_id, 2, EventType.FILLED, quantity, price, at))


# --- Side derivation ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("leg_side", "opening", "closing"), [("buy", "buy", "sell"), ("sell", "sell", "buy")]
)
def test_sides_are_derived_from_the_leg_direction(leg_side, opening, closing):
    assert derive_side("open", leg_side) == opening
    assert derive_side("close", leg_side) == closing
    assert derive_side("increase", leg_side) == opening  # reserved ops derive consistently
    assert derive_side("reduce", leg_side) == closing


def test_no_exit_side_is_stored_anywhere_in_the_intent():
    assert {f.name for f in fields(intent("x"))}.isdisjoint({"exit_action", "exit_side"})


# --- Intent identity ---------------------------------------------------------------------


def test_intent_ids_are_deterministic_and_pinned():
    first = make_intent_id("v1", RULE, ts(3), 0, "stock")
    assert first == make_intent_id("v1", RULE, ts(3), 0, "stock")
    # Locks the canonical representation; a change here is a change of every stored id.
    assert first == "69385ad79d02762b908773759c8e759342bf1b90e84193e0bad29ea60b10bdcb"


@pytest.mark.parametrize(
    "changed",
    [
        dict(strategy_version_id="v2"),
        dict(source=OperationSource("rule", "other")),
        dict(source=OperationSource("risk", "enter")),
        dict(bar_timestamp=ts(4)),
        dict(op_index=1),
        dict(leg_id="other"),
    ],
)
def test_each_identity_input_changes_the_intent_id(changed):
    base = dict(
        strategy_version_id="v1", source=RULE, bar_timestamp=ts(3), op_index=0, leg_id="stock"
    )
    assert make_intent_id(**base) != make_intent_id(**{**base, **changed})


def test_group_id_is_shared_by_legs_and_differs_from_intent_ids():
    group = make_group_id("v1", RULE, ts(3), 0)
    assert group == make_group_id("v1", RULE, ts(3), 0)
    assert group != make_group_id("v1", RULE, ts(3), 1)
    assert group != make_intent_id("v1", RULE, ts(3), 0, "stock")


def test_equal_instants_in_different_zones_give_the_same_id():
    from datetime import timedelta, timezone

    ist = timezone(timedelta(hours=5, minutes=30))
    assert make_intent_id("v1", RULE, ts(3), 0, "s") == make_intent_id(
        "v1", RULE, ts(3).astimezone(ist), 0, "s"
    )


def test_naive_timestamps_are_rejected():
    from datetime import datetime

    with pytest.raises(ValueError):
        make_intent_id("v1", RULE, datetime(2025, 1, 1), 0, "s")


def test_ids_carry_no_randomness_or_clock():
    import ast
    import inspect

    from app.strategy_definition.runtime import intents

    tree = ast.parse(inspect.getsource(intents))
    imported = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0] for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imported.isdisjoint({"uuid", "random", "secrets", "time", "os"})
    called = {node.func.attr for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert called.isdisjoint({"now", "utcnow", "today", "uuid4", "getpid"})


# --- Planner -----------------------------------------------------------------------------


def planner(definition, allocation="10000"):
    return OrderPlanner(
        definition, strategy_version_id="v1", allocation=D(allocation),
        resolver=PrimaryInstrumentResolver(),
    )


def candidate(op_name="open", source=RULE):
    return CandidateOperation(source, 0, op(op_name), 0)


def snap_for(book: Ledger):
    return book.snapshot().position("main")


def test_open_sizes_from_explicit_shares_and_derives_the_leg_side():
    for side in ("buy", "sell"):
        defn = long_definition(positions=(position(legs=[leg(side=side, quantity="2")]),))
        (planned,) = planner(defn).plan(
            candidate(), snap_for(ledger()), bar_timestamp=ts(1), reference_price=D(50)
        )
        assert (planned.side, planned.quantity, planned.op) == (side, D(20), "open")  # 10 x 2
        assert planned.intent_id == make_intent_id("v1", RULE, ts(1), 0, "stock")
        assert planned.signal_ts == ts(1) and planned.constraints.reference_price == D(50)
        assert planned.contract.kind == "primary"


def test_close_trades_against_the_leg_for_the_held_quantity():
    book = ledger()
    opening = intent("o1", "open", "sell", "7")
    book.track_order(opening)
    fill(book, opening)
    defn = long_definition(positions=(position(legs=[leg(side="sell")]),))
    (planned,) = planner(defn).plan(
        candidate("close"), snap_for(book), bar_timestamp=ts(2), reference_price=D(90)
    )
    assert (planned.side, planned.quantity) == ("buy", D(7))


def test_v1_all_in_sizing_is_an_explicit_unit_resolved_against_the_allocation():
    defn = long_definition(positions=(replace(position(), sizing=PercentOfAllocationSizing(D(100))),))
    (planned,) = planner(defn, "50000").plan(
        candidate(), snap_for(ledger()), bar_timestamp=ts(1), reference_price=D(92)
    )
    assert planned.quantity == D(50000) / D(92)  # exactly V1's initial_capital / entry_price
    shares = long_definition(positions=(replace(position(), sizing=SharesSizing(D(3))),))
    (planned,) = planner(shares, "50000").plan(
        candidate(), snap_for(ledger()), bar_timestamp=ts(1), reference_price=D(92)
    )
    assert planned.quantity == D(3)  # capital plays no part in explicit sizing


@pytest.mark.parametrize("name", ["increase", "reduce"])
def test_planner_refuses_reserved_operations(name):
    with pytest.raises(UnsupportedOperationError):
        planner(long_definition()).plan(
            candidate(name), snap_for(ledger()), bar_timestamp=ts(1), reference_price=D(1)
        )


def test_planner_rejects_a_non_positive_reference_price():
    with pytest.raises(RuntimeDataError):
        planner(long_definition()).plan(
            candidate(), snap_for(ledger()), bar_timestamp=ts(1), reference_price=D(0)
        )


# --- Simulated execution -----------------------------------------------------------------


BAR = ExecutionBar(ts(5), D(123))


def test_complete_fill_is_accepted_then_filled_at_the_bar_close():
    order = intent("a")
    accepted, filled = SimulatedExecutionAdapter().submit(order, BAR)
    assert (accepted.type, accepted.event_seq) == (EventType.ACCEPTED, 1)
    assert (filled.type, filled.event_seq) == (EventType.FILLED, 2)
    assert (filled.filled_qty, filled.price, filled.ts) == (order.quantity, D(123), ts(5))
    assert accepted.intent_id == filled.intent_id == order.intent_id


def test_reject_is_an_event_not_an_exception():
    (rejected,) = SimulatedExecutionAdapter(behavior=lambda i: Reject("no_liquidity")).submit(
        intent("a"), BAR
    )
    assert (rejected.type, rejected.reason, rejected.filled_qty) == (
        EventType.REJECTED, "no_liquidity", None,
    )


def test_partial_fill_event_shape():
    adapter = SimulatedExecutionAdapter(behavior=lambda i: PartialFill(D(4)))
    accepted, partial, expired = adapter.submit(intent("a", quantity="10"), BAR)
    assert [e.type for e in (accepted, partial, expired)] == [
        EventType.ACCEPTED, EventType.PARTIAL_FILL, EventType.EXPIRED,
    ]
    assert (partial.filled_qty, partial.price) == (D(4), D(123))
    assert [e.event_seq for e in (accepted, partial, expired)] == [1, 2, 3]


def test_resubmitting_an_intent_id_is_the_same_order():
    adapter = SimulatedExecutionAdapter()
    assert adapter.submit(intent("a"), BAR) is adapter.submit(intent("a"), BAR)


def test_next_bar_open_is_refused_not_approximated():
    with pytest.raises(ExecutionError):
        SimulatedExecutionAdapter("next_bar_open")


def test_event_serialisation_is_canonical():
    event = ev("a", 2, EventType.FILLED, "1.5", "100")
    assert event.to_dict()["filled_qty"] == "1.5" and event.to_dict()["type"] == "filled"


# --- Ledger ------------------------------------------------------------------------------


def test_tracking_an_order_changes_status_but_never_holdings():
    book = ledger()
    book.track_order(intent("a", quantity="10"))
    assert book.status("main") is PositionStatus.OPENING  # intent in flight
    assert book.held("main", "stock") == 0  # nothing is held until a fill
    assert book.cash == D(10000)


def test_lifecycle_flat_opening_open_closing_flat():
    book = ledger()
    assert book.status("main") is PositionStatus.FLAT
    opening = intent("o", "open", "buy", "10")
    book.track_order(opening)
    assert book.status("main") is PositionStatus.OPENING
    book.apply_event(ev("o", 1, EventType.ACCEPTED))
    assert book.status("main") is PositionStatus.OPENING
    book.apply_event(ev("o", 2, EventType.FILLED, "10", "100"))
    assert book.status("main") is PositionStatus.OPEN
    closing = intent("c", "close", "sell", "10", at=1, source=OperationSource("rule", "exit"))
    book.track_order(closing)
    assert book.status("main") is PositionStatus.CLOSING
    book.apply_event(ev("c", 1, EventType.ACCEPTED, at=1))
    book.apply_event(ev("c", 2, EventType.FILLED, "10", "110", at=1))
    assert book.status("main") is PositionStatus.FLAT


def test_quantity_average_price_pnl_equity_and_trade_lifecycle():
    book = ledger("10000")
    opening = intent("o", "open", "buy", "10", at=1)
    book.track_order(opening)
    fill(book, opening, "100", at=1)
    assert (book.held("main", "stock"), book.average_entry_price("main", "stock")) == (D(10), D(100))
    assert book.unrealised_pnl({("main", "stock"): D(112)}) == D(120)
    assert book.equity({("main", "stock"): D(112)}) == D(10120)
    assert book.cash + book.market_value({("main", "stock"): D(112)}) == D(10120)

    closing = intent("c", "close", "sell", "10", at=3, source=OperationSource("rule", "exit"))
    book.track_order(closing)
    fill(book, closing, "112", at=3)
    assert book.realised_pnl == D(120) and book.equity({}) == D(10120)
    (trade,) = book.trades
    assert (trade.signal_ts, trade.fill_ts) == (ts(1), ts(1))
    assert (trade.exit_signal_ts, trade.exit_fill_ts, trade.exit_reason) == (ts(3), ts(3), "rule:exit")
    (trade_leg,) = trade.legs
    assert (trade_leg.side, trade_leg.quantity, trade_leg.entry_price, trade_leg.exit_price) == (
        "long", D(10), D(100), D(112),
    )
    assert trade.pnl == D(120)


def test_short_pnl_has_the_opposite_sign():
    spec = LedgerPositionSpec("main", (LedgerLegSpec("stock", "sell", D(1)),))
    book = Ledger([spec], D(1000))
    opening = intent("o", "open", "sell", "5")
    book.track_order(opening)
    fill(book, opening, "100")
    assert book.held("main", "stock") == D(-5)
    assert book.equity({("main", "stock"): D(90)}) == D(1050)
    closing = intent("c", "close", "buy", "5", at=1)
    book.track_order(closing)
    fill(book, closing, "90", at=1)
    assert book.trades[0].legs[0].side == "short" and book.trades[0].pnl == D(50)


def test_engine_issued_exit_is_not_a_signal():
    book = ledger()
    opening = intent("o", "open", "buy", "1")
    book.track_order(opening)
    fill(book, opening)
    closing = intent("c", "close", "sell", "1", at=2, source=OperationSource("engine", "end_of_data"))
    book.track_order(closing)
    fill(book, closing, at=2)
    assert book.trades[0].exit_signal_ts is None and book.trades[0].exit_reason == "end_of_data"


def test_partial_fill_then_expiry_leaves_a_smaller_open_position():
    book = ledger()
    order = intent("o", quantity="10")
    book.track_order(order)
    book.apply_event(ev("o", 1, EventType.ACCEPTED))
    book.apply_event(ev("o", 2, EventType.PARTIAL_FILL, "4", "100"))
    assert book.status("main") is PositionStatus.OPENING and book.held("main", "stock") == D(4)
    book.apply_event(ev("o", 3, EventType.EXPIRED))
    assert book.status("main") is PositionStatus.OPEN and book.held("main", "stock") == D(4)


def test_rejected_open_leaves_the_position_flat():
    book = ledger()
    book.track_order(intent("o"))
    book.apply_event(ev("o", 1, EventType.REJECTED, reason="no_funds"))
    assert book.status("main") is PositionStatus.FLAT and book.cash == D(10000)
    assert book.trades == ()


def test_rejected_close_leaves_the_position_open():
    book = ledger()
    opening = intent("o", quantity="3")
    book.track_order(opening)
    fill(book, opening)
    book.track_order(intent("c", "close", "sell", "3", at=1))
    book.apply_event(ev("c", 1, EventType.REJECTED, at=1))
    assert book.status("main") is PositionStatus.OPEN and book.held("main", "stock") == D(3)


def test_incomplete_leg_set_degrades_the_position():
    spec = LedgerPositionSpec(
        "main", (LedgerLegSpec("call", "buy", D(1)), LedgerLegSpec("put", "buy", D(1)))
    )
    book = Ledger([spec], D(10000))
    call, put = intent("call", leg="call"), intent("put", leg="put")
    book.track_order(call)
    book.track_order(put)
    fill(book, call)
    book.apply_event(ev("put", 1, EventType.REJECTED))
    assert book.status("main") is PositionStatus.DEGRADED
    book.track_order(intent("unwind", "close", "sell", "10", leg="call", at=1))
    fill(book, intent("unwind", "close", "sell", "10", leg="call", at=1), at=1)
    assert book.status("main") is PositionStatus.FLAT


def test_duplicate_events_are_idempotent_and_conflicting_ones_raise():
    book = ledger()
    order = intent("o", quantity="10")
    book.track_order(order)
    book.apply_event(ev("o", 1, EventType.ACCEPTED))
    book.apply_event(ev("o", 1, EventType.ACCEPTED))  # exact duplicate: ignored
    assert len(book.journal) == 2
    with pytest.raises(LedgerInconsistencyError):
        book.apply_event(ev("o", 1, EventType.REJECTED))


@pytest.mark.parametrize(
    "events",
    [
        [ev("ghost", 1, EventType.ACCEPTED)],  # unknown intent
        [ev("o", 1, EventType.FILLED, "10", "100")],  # fill before acceptance
        [ev("o", 1, EventType.ACCEPTED), ev("o", 2, EventType.FILLED, "11", "100")],  # over-fill
        [ev("o", 1, EventType.ACCEPTED), ev("o", 2, EventType.FILLED, "4", "100")],  # short 'filled'
        [ev("o", 1, EventType.ACCEPTED), ev("o", 2, EventType.PARTIAL_FILL, "10", "100")],
        [ev("o", 1, EventType.ACCEPTED), ev("o", 2, EventType.FILLED, "10", "0")],  # no price
        [ev("o", 2, EventType.ACCEPTED), ev("o", 1, EventType.REJECTED)],  # seq regresses
        [ev("o", 1, EventType.ACCEPTED), ev("o", 2, EventType.FILLED, "10", "100"),
         ev("o", 3, EventType.EXPIRED)],  # event after a terminal state
    ],
)
def test_inconsistent_event_streams_raise(events):
    book = ledger()
    book.track_order(intent("o", quantity="10"))
    with pytest.raises(LedgerInconsistencyError):
        for event in events:
            book.apply_event(event)


def test_a_fill_that_would_flip_the_position_raises():
    book = ledger()
    opening = intent("o", quantity="2")
    book.track_order(opening)
    fill(book, opening)
    oversell = intent("c", "close", "sell", "5", at=1)
    book.track_order(oversell)
    with pytest.raises(LedgerInconsistencyError):
        fill(book, oversell, at=1)


def test_duplicate_or_unknown_order_registration_raises():
    book = ledger()
    book.track_order(intent("o"))
    with pytest.raises(LedgerInconsistencyError):
        book.track_order(intent("o"))
    with pytest.raises(LedgerInconsistencyError):
        book.track_order(intent("p", leg="nope"))


def test_decimal_accounting_is_deterministic_and_never_float():
    def run():
        book = ledger("50000")
        opening = intent("o", quantity=str(D(50000) / D(92)))
        book.track_order(opening)
        fill(book, opening, "92")
        marks = {("main", "stock"): D("105.1")}
        return book.equity(marks), book.cash, book.unrealised_pnl(marks)

    first = run()
    assert first == run()
    assert all(isinstance(value, Decimal) for value in first)
    equity, cash, _ = first
    assert abs(equity - (cash + D(50000) / D(92) * D("105.1"))) < D("1e-18")


def test_replaying_the_journal_rebuilds_an_identical_ledger():
    book = ledger("10000")
    opening = intent("o", quantity="10", at=1)
    book.track_order(opening)
    fill(book, opening, "100", at=1)
    closing = intent("c", "close", "sell", "10", at=4, source=OperationSource("rule", "exit"))
    book.track_order(closing)
    fill(book, closing, "95", at=4)
    twin = Ledger.replay([SPEC], D(10000), book.journal)
    assert (twin.snapshot(), twin.trades, twin.cash, twin.realised_pnl, twin.equity({})) == (
        book.snapshot(), book.trades, book.cash, book.realised_pnl, book.equity({}),
    )
    assert any(isinstance(entry, OrderRegistration) for entry in book.journal)


def test_ledger_specs_come_from_the_canonical_definition():
    (spec,) = ledger_specs(long_definition(positions=(position(legs=[leg(side="sell", quantity="2")]),)))
    assert spec.position_id == "main" and spec.legs[0].side == "sell" and spec.legs[0].ratio == D(2)
