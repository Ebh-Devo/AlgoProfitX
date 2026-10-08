"""V1 parity gate: the V2 runtime reproduces EmaCrossoverReferenceEngine under same_bar_close."""

import json

import pytest

from app.backtesting.reference import EmaCrossoverReferenceEngine
from app.strategy_definition.runtime import StrategyRuntimeEngine
from tests.strategy_v2_parity_support import CAPITAL, CASES, GOLDEN_PATH, candles, v1_parity_record
from tests.strategy_v2_runtime_support import (
    RUNTIME_GOLDEN_PATH,
    compute_runtime_case,
    runtime_parity_record,
)

GOLDEN = json.loads(RUNTIME_GOLDEN_PATH.read_text(encoding="utf-8"))
PHASE1_GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
BY_NAME = {case["name"]: case for case in GOLDEN["cases"]}
TRADE_FIELDS = {
    "side", "signal_timestamp", "fill_timestamp", "exit_signal_timestamp", "exit_fill_timestamp",
    "quantity", "entry_price", "exit_price", "pnl", "exit_reason",
}
NAMES = [spec["name"] for spec in CASES]


def test_golden_covers_every_phase1_case():
    assert [case["name"] for case in GOLDEN["cases"]] == NAMES


@pytest.mark.parametrize("spec", CASES, ids=NAMES)
def test_golden_fixture_is_locked(spec):
    assert compute_runtime_case(spec) == BY_NAME[spec["name"]]


@pytest.mark.parametrize("name", NAMES)
def test_v1_side_of_the_fixture_is_the_phase1_oracle_record(name):
    # Regenerating this fixture cannot weaken V1's expected values: they must equal the
    # independently committed Phase 1 record.
    phase1 = next(case for case in PHASE1_GOLDEN["cases"] if case["name"] == name)
    assert BY_NAME[name]["v1"] == phase1["v1_parity"]


@pytest.mark.parametrize("spec", CASES, ids=NAMES)
def test_runtime_matches_the_live_v1_engine_exactly(spec):
    series = candles(spec["closes"])
    configuration = spec["v1_configuration"]
    v1 = EmaCrossoverReferenceEngine("p").run(configuration, CAPITAL, series)
    runtime = StrategyRuntimeEngine("p", "parity").run(configuration, CAPITAL, series)

    # Every required output, individually, so a failure names the field that moved.
    assert runtime.final_equity == v1.final_equity
    assert runtime.total_return == v1.total_return
    assert runtime.equity_curve == v1.equity_curve  # complete curve, exact strings
    record, oracle = runtime_parity_record(runtime), v1_parity_record(configuration, v1, series)
    assert record == oracle
    assert record == BY_NAME[spec["name"]]["runtime"]
    for trade in record["trades"]:
        assert set(trade) == TRADE_FIELDS
        assert trade["signal_timestamp"] == trade["fill_timestamp"]  # same_bar_close


@pytest.mark.parametrize("name", NAMES)
def test_runtime_trades_keep_the_v1_trade_keys(name):
    case = BY_NAME[name]
    result = StrategyRuntimeEngine("p", "parity").run(
        case["v1_configuration"], CAPITAL, candles(case["closes"])
    )
    v1 = EmaCrossoverReferenceEngine("p").run(
        case["v1_configuration"], CAPITAL, candles(case["closes"])
    )
    for trade, v1_trade in zip(result.trades, v1.trades):
        assert {key: trade[key] for key in v1_trade} == v1_trade
    assert result.engine_identifier == "strategy-runtime-v2"


def test_exit_reasons_are_the_documented_mapping():
    reasons = {name: [t["exit_reason"] for t in c["runtime"]["trades"]] for name, c in BY_NAME.items()}
    assert reasons == {
        "long_with_exit": ["rule:exit"],
        "short_with_exit": ["rule:exit"],
        "legacy_entry_only": ["end_of_data"],
        "long_exit_never_crosses": ["end_of_data"],
        "no_entry_signal": [],
    }
