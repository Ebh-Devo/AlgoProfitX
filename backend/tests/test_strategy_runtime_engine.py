"""StrategyRuntimeEngine end to end: V2 definitions, no lookahead, replay, refusals."""

from dataclasses import replace

import pytest

from app.backtesting.contracts import BacktestExecutionError
from app.strategy_definition.evaluator import InvalidEvaluationRequestError
from app.strategy_definition.runtime import (
    LedgerInconsistencyError,
    RuntimeDataError,
    RuntimeSetupError,
    StrategyRuntimeEngine,
    UnsupportedOperationError,
)
from app.strategy_definition.runtime import engine as engine_module
from app.strategy_definition.runtime.execution import EventType, Reject
from app.strategy_definition.runtime.execution import SimulatedExecutionAdapter
from app.strategy_definition.runtime.ledger import Ledger, ledger_specs
from app.strategy_definition.runtime.market import BarCursorContext, compute_indicator_series
from app.strategy_definition.schema import (
    CompareCondition, ConstantOperand, CrossCondition, RiskDefinition, SharesSizing,
)
from tests.strategy_v2_builders import (
    CLOSE, D, ind, leg, long_definition, op, position, rule, stop,
)
from tests.strategy_v2_parity_support import (
    CAPITAL, DOWN_UP_DOWN, EMA_3_9_LONG_ENTRY, EMA_3_9_LONG_EXIT, UP_DOWN_UP, candles,
)

V2_ENV = {"initial_capital": 50000, "fill_model": "same_bar_close"}


def ema_definition(side="buy", shares=10, **changes):
    entry, exit_ = ("above", "below") if side == "buy" else ("below", "above")
    return long_definition(
        positions=(position(legs=[leg(side=side)], sizing=SharesSizing(D(shares))),),
        rules=(
            rule("enter", CrossCondition(entry, ind("ema", 3), ind("ema", 9)), [op("open")]),
            rule("exit", CrossCondition(exit_, ind("ema", 3), ind("ema", 9)), [op("close")]),
        ),
        **changes,
    )


def engine(**kwargs):
    return StrategyRuntimeEngine("test", "version-1", **kwargs)


def run_v2(definition=None, closes=DOWN_UP_DOWN, env=None, **kwargs):
    definition = definition or ema_definition()
    return engine(**kwargs).run_detailed(definition.to_dict(), env or V2_ENV, candles(closes))


# --- V2 definitions run through the shared runtime ---------------------------------------


def test_v2_long_uses_explicit_shares_not_capital():
    run = run_v2()
    intents = [i for outcome in run.outcomes for i in outcome.intents]
    assert [(i.op, i.side, i.quantity) for i in intents] == [("open", "buy", D(10)), ("close", "sell", D(10))]
    (trade,) = run.trades
    assert (trade.legs[0].entry_price, trade.legs[0].exit_price, trade.pnl) == (D(92), D(105), D(130))
    assert run.final_equity == D(50130)


def test_v2_short_opens_sell_and_closes_buy():
    run = run_v2(ema_definition("sell"), UP_DOWN_UP)
    intents = [i for outcome in run.outcomes for i in outcome.intents]
    assert [(i.op, i.side) for i in intents] == [("open", "sell"), ("close", "buy")]
    assert run.trades[0].legs[0].side == "short"


def test_status_follows_the_ledger_through_a_run():
    run = run_v2()
    (opened,) = [o for o in run.outcomes if o.intents and o.intents[0].op == "open"]
    assert [e.type for e in opened.events] == [EventType.ACCEPTED, EventType.FILLED]
    rebuilt = Ledger.replay(ledger_specs(ema_definition()), D(50000), run.journal)
    assert rebuilt.status("main").value == "flat" and len(rebuilt.trades) == 1


def test_a_v2_run_requires_an_explicit_fill_model():
    with pytest.raises(RuntimeSetupError, match="fill_model"):
        run_v2(env={"initial_capital": 50000})


def test_lifted_v1_carries_its_environment_default_fill_model():
    config = {"entry": EMA_3_9_LONG_ENTRY, "exit": EMA_3_9_LONG_EXIT}
    result = engine().run(config, CAPITAL, candles(DOWN_UP_DOWN))
    assert result.trades[0]["exit_reason"] == "rule:exit"


@pytest.mark.parametrize("env", [{"initial_capital": 50000, "fill_model": "next_bar_open"}])
def test_next_bar_open_is_not_silently_approximated(env):
    with pytest.raises(BacktestExecutionError):
        engine().run(ema_definition().to_dict(), env, candles(DOWN_UP_DOWN))


def test_end_of_data_liquidation_can_be_turned_off():
    closes = [100 - i for i in range(15)] + [86 + 2 * i for i in range(10)]
    held = run_v2(closes=closes, liquidate_at_end=False)
    assert held.trades == () and held.final_equity != D(50000)  # still open, marked to market
    flat = run_v2(closes=closes)
    assert flat.trades[0].exit_reason == "end_of_data"
    assert flat.final_equity == held.final_equity


def test_rejected_open_never_creates_a_position():
    adapter = SimulatedExecutionAdapter(behavior=lambda i: Reject("no_funds"))
    run = run_v2(adapter=adapter)
    assert run.trades == () and run.final_equity == D(50000)
    assert any(i.op == "open" for o in run.outcomes for i in o.intents)
    assert all(e.type is EventType.REJECTED for o in run.outcomes for e in o.events)


def test_open_signal_on_a_position_that_is_already_open_is_skipped_and_recorded():
    closes = DOWN_UP_DOWN
    definition = long_definition(
        rules=(rule("always", CompareCondition("gt", CLOSE, ConstantOperand(D(0))), [op("open")]),),
        positions=(position(sizing=SharesSizing(D(1))),),
    )
    run = engine().run_detailed(definition.to_dict(), V2_ENV, candles(closes))
    skipped = [s.reason for o in run.outcomes for s in o.skipped]
    assert skipped and set(skipped) == {"already_open"}
    assert len([i for o in run.outcomes for i in o.intents if i.op == "open"]) == 1


# --- Setup refusals ----------------------------------------------------------------------


def test_capabilities_the_runtime_lacks_are_refused_before_any_candle():
    rsi = long_definition(
        rules=(
            rule("e", CompareCondition("lt", ind("rsi", 14), ConstantOperand(D(30))), [op("open")]),
            rule("x", CompareCondition("gt", ind("rsi", 14), ConstantOperand(D(70))), [op("close")]),
        )
    )
    two_legs = long_definition(positions=(position(legs=[leg("a"), leg("b")]),))
    risk = long_definition(
        positions=(position(risk=RiskDefinition(stop_loss=stop())),),
    )
    for definition, missing in [
        (rsi, "indicator.rsi@1"),
        (two_legs, "multi_leg.basket"),
        (risk, "risk.stop_loss"),
    ]:
        with pytest.raises(RuntimeSetupError, match=missing.replace(".", r"\.")):
            engine().run_detailed(definition.to_dict(), V2_ENV, candles(DOWN_UP_DOWN))
    run_v2()  # control: the same runtime runs the supported definition


def test_increase_and_reduce_are_unsupported_capabilities():
    from app.strategy_definition.schema import Amount

    amount = Amount("fraction_of_open", D("0.5"))
    for name in ("increase", "reduce"):
        definition = long_definition(
            rules=(
                rule("e", CrossCondition("above", ind("ema", 3), ind("ema", 9)), [op("open")]),
                rule("s", CrossCondition("above", ind("ema", 3), ind("ema", 9)), [op(name, amount=amount)]),
            )
        )
        with pytest.raises(RuntimeSetupError, match=f"op.{name}"):
            engine().run_detailed(definition.to_dict(), V2_ENV, candles(DOWN_UP_DOWN))


def test_an_invalid_definition_is_a_setup_error_with_issues():
    only_close = long_definition(
        rules=(rule("x", CrossCondition("below", ind("ema", 3), ind("ema", 9)), [op("close")]),)
    )
    with pytest.raises(RuntimeSetupError) as caught:
        engine().run_detailed(only_close.to_dict(), V2_ENV, candles(DOWN_UP_DOWN))
    assert caught.value.issues


def test_a_malformed_document_is_a_setup_error_and_a_backtest_error_via_run():
    with pytest.raises(RuntimeSetupError):
        engine().run_detailed({"schema_version": 2}, V2_ENV, candles(DOWN_UP_DOWN))
    with pytest.raises(BacktestExecutionError):
        engine().run({"entry": {"type": "nope"}}, CAPITAL, candles(DOWN_UP_DOWN))


@pytest.mark.parametrize("env", [{"fill_model": "same_bar_close"}, {"initial_capital": 0, "fill_model": "same_bar_close"},
                                 {"initial_capital": "abc", "fill_model": "same_bar_close"},
                                 {**V2_ENV, "timeframe": "5m"}])
def test_bad_environment_is_a_setup_error(env):
    with pytest.raises(RuntimeSetupError):
        run_v2(env=env)


def test_strategy_version_id_is_required_for_deterministic_ids():
    with pytest.raises(RuntimeSetupError):
        StrategyRuntimeEngine("p", "").run_detailed(ema_definition().to_dict(), V2_ENV, candles(DOWN_UP_DOWN))


def test_unsupported_indicator_calculation_is_a_setup_error():
    definition = long_definition(
        rules=(rule("e", CompareCondition("gt", ind("sma", 3), ConstantOperand(D(1))), [op("open")]),)
    )
    with pytest.raises(RuntimeSetupError):
        compute_indicator_series(definition, candles(DOWN_UP_DOWN))


# --- Data errors -------------------------------------------------------------------------


def test_data_problems_are_runtime_data_errors_not_false_conditions():
    series = list(candles(DOWN_UP_DOWN))
    naive = [replace(series[0], timestamp=series[0].timestamp.replace(tzinfo=None))] + series[1:]
    for bad in ([], series[::-1], naive, [series[0], series[0]]):
        with pytest.raises(RuntimeDataError):
            engine().run_detailed(ema_definition().to_dict(), V2_ENV, bad)
        with pytest.raises(BacktestExecutionError):
            engine().run(ema_definition().to_dict(), V2_ENV, bad)


def test_error_kinds_are_distinct_types():
    kinds = {RuntimeSetupError, UnsupportedOperationError, RuntimeDataError, LedgerInconsistencyError}
    assert len(kinds) == 4 and not any(issubclass(a, b) for a in kinds for b in kinds if a is not b)


# --- No lookahead ------------------------------------------------------------------------


def test_evaluation_at_t_never_touches_a_later_bar(monkeypatch):
    reads = []

    class Spy(BarCursorContext):
        def _position(self, offset):
            position = super()._position(offset)
            reads.append((self._index, position))
            return position

    monkeypatch.setattr(engine_module, "BarCursorContext", Spy)
    run_v2()
    assert reads and all(position is None or position <= index for index, position in reads)


def test_the_context_refuses_a_future_offset():
    series = candles(DOWN_UP_DOWN)
    context = BarCursorContext(series, {}, 5)
    with pytest.raises(InvalidEvaluationRequestError):
        context.price("close", 1)


def test_outcomes_up_to_t_are_independent_of_everything_after_t():
    full = run_v2(liquidate_at_end=False)
    for cut in (20, 31, 40):
        truncated = engine(liquidate_at_end=False).run_detailed(
            ema_definition().to_dict(), V2_ENV, candles(DOWN_UP_DOWN[:cut])
        )
        assert truncated.outcomes == full.outcomes[:cut]
        assert truncated.equity_curve == full.equity_curve[:cut]


def test_rewriting_the_future_does_not_change_the_past():
    base = list(DOWN_UP_DOWN)
    altered = base[:30] + [1000 - 7 * i for i in range(15)]
    first = run_v2(closes=base, liquidate_at_end=False)
    second = run_v2(closes=altered, liquidate_at_end=False)
    assert first.outcomes[:30] == second.outcomes[:30]
    assert first.equity_curve[:30] == second.equity_curve[:30]


# --- Replay ------------------------------------------------------------------------------


def test_replaying_the_same_data_reproduces_everything():
    first, second = run_v2(), run_v2()
    assert first.outcomes == second.outcomes
    assert [i for o in first.outcomes for i in o.intents] == [i for o in second.outcomes for i in o.intents]
    assert [e for o in first.outcomes for e in o.events] == [e for o in second.outcomes for e in o.events]
    assert (first.trades, first.journal, first.equity_curve, first.final_equity) == (
        second.trades, second.journal, second.equity_curve, second.final_equity,
    )
    rebuilt = Ledger.replay(ledger_specs(ema_definition()), D(50000), first.journal)
    assert rebuilt.trades == first.trades and rebuilt.realised_pnl == first.final_equity - D(50000)


def test_intent_ids_depend_on_strategy_version_but_not_on_the_run():
    ids = lambda run: [i.intent_id for o in run.outcomes for i in o.intents]  # noqa: E731
    assert ids(run_v2()) == ids(run_v2())
    other = StrategyRuntimeEngine("test", "version-2").run_detailed(
        ema_definition().to_dict(), V2_ENV, candles(DOWN_UP_DOWN)
    )
    assert set(ids(other)).isdisjoint(ids(run_v2()))
    assert len(set(ids(run_v2()))) == len(ids(run_v2()))  # entry and exit differ


# --- Documented divergence from V1 -------------------------------------------------------


def test_v2_can_trade_again_after_an_exit_unlike_the_v1_reference_engine():
    """V1 takes at most one trade per run; the V2 rules do not stop after the first exit.

    This is a real semantic difference, outside the parity fixtures (none has a second entry
    cross after an exit), and is reported rather than papered over.
    """
    from app.backtesting.reference import EmaCrossoverReferenceEngine

    closes = DOWN_UP_DOWN + [114 - 45 + 3 * i for i in range(30)] + [99 - 4 * i for i in range(15)]
    config = {"entry": EMA_3_9_LONG_ENTRY, "exit": EMA_3_9_LONG_EXIT}
    v1 = EmaCrossoverReferenceEngine("p").run(config, CAPITAL, candles(closes))
    v2 = engine().run(config, CAPITAL, candles(closes))
    assert len(v1.trades) == 1
    assert len(v2.trades) > 1
    assert v2.trades[0] == {**v2.trades[0], **{k: v for k, v in v1.trades[0].items()}}  # first trade agrees
