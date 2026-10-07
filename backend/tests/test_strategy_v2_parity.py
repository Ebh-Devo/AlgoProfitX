"""Golden V1 / V2 parity: the canonical V2 definition lifted from V1 loses no semantics."""

import json
from dataclasses import replace

import pytest

from app.strategy_definition import load_definition
from tests.strategy_v2_parity_support import (
    CASES,
    GOLDEN_PATH,
    candles,
    compute_case,
    run_v2_compat_seam,
)

GOLDEN = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
BY_NAME = {case["name"]: case for case in GOLDEN["cases"]}
TRADE_FIELDS = {
    "side", "signal_timestamp", "fill_timestamp", "exit_signal_timestamp", "exit_fill_timestamp",
    "quantity", "entry_price", "exit_price", "pnl", "exit_reason",
}


def test_golden_covers_every_case():
    assert [case["name"] for case in GOLDEN["cases"]] == [spec["name"] for spec in CASES]


@pytest.mark.parametrize("spec", CASES, ids=[spec["name"] for spec in CASES])
def test_golden_fixture_is_locked(spec):
    # Recomputing from source must reproduce the committed file exactly (deterministic).
    assert compute_case(spec) == BY_NAME[spec["name"]]


@pytest.mark.parametrize("name", list(BY_NAME))
def test_v2_representation_reproduces_v1_exactly(name):
    case = BY_NAME[name]
    v1, v2 = case["v1_parity"], case["v2_parity"]
    assert v2 == v1  # trade count, side, qty, prices, pnl, timestamps, exit reason, equity curve
    assert v1["trade_count"] == len(v1["trades"])
    assert len(v1["equity_curve"]) == len(case["closes"])
    for trade in v1["trades"]:
        assert set(trade) == TRADE_FIELDS
        assert trade["signal_timestamp"] == trade["fill_timestamp"]  # same_bar_close
        assert trade["exit_reason"] in {"rule:exit", "end_of_data"}
        assert (trade["exit_signal_timestamp"] is None) == (trade["exit_reason"] == "end_of_data")
    if v1["trades"]:
        assert v1["equity_curve"][-1]["equity"] == v1["final_equity"]


@pytest.mark.parametrize("name", list(BY_NAME))
def test_stored_v2_definition_is_the_adapter_output(name):
    case = BY_NAME[name]
    loaded = load_definition(case["v1_configuration"])
    assert case["v2_definition"] == loaded.definition.to_dict()
    assert case["v2_fill_model"] == "same_bar_close" == loaded.fill_model


@pytest.mark.parametrize("name", [n for n, c in BY_NAME.items() if c["v1_parity"]["trade_count"]])
def test_seam_reads_the_v2_definition(name):
    # Changing a semantic in the lifted definition changes the outcome, so the seam is not
    # secretly reading the V1 configuration.
    case = BY_NAME[name]
    loaded = load_definition(case["v1_configuration"])
    (position,) = loaded.definition.positions
    flipped_leg = replace(position.legs[0], side="sell" if position.legs[0].side == "buy" else "buy")
    flipped = replace(loaded.definition, positions=(replace(position, legs=(flipped_leg,)),))
    result = run_v2_compat_seam(flipped, loaded.fill_model, case["backtest_configuration"], candles(case["closes"]))
    assert result != case["v1_parity"]


def test_legacy_defaults_are_explicit_in_the_fixture():
    definition = BY_NAME["legacy_entry_only"]["v2_definition"]
    assert definition["positions"]["main"]["legs"][0]["side"] == "buy"
    assert [rule["id"] for rule in definition["rules"]] == ["enter"]
    assert definition["rules"][0]["when"]["dir"] == "above"
    assert "action" not in BY_NAME["legacy_entry_only"]["v1_configuration"]["entry"]
