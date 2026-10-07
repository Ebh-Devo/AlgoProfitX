import copy
from decimal import Decimal

import pytest

from app.strategy_definition import (
    StrategyDefinitionError,
    adapt_v1_definition,
    load_definition,
    load_v2_definition,
)
from app.strategy_definition.schema import CrossCondition, PercentOfAllocationSizing

LONG = {
    "entry": {"type": "ema_crossover", "action": "buy", "direction": "above", "fast_period": 3, "slow_period": 9},
    "exit": {"type": "ema_crossover", "action": "sell", "direction": "below", "fast_period": 3, "slow_period": 9},
}
SHORT = {
    "entry": {"type": "ema_crossover", "action": "sell", "direction": "below", "fast_period": 3, "slow_period": 9},
    "exit": {"type": "ema_crossover", "action": "buy", "direction": "above", "fast_period": 3, "slow_period": 9},
}
LEGACY = {"entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 9}}


def summary(definition):
    (position,) = definition.positions
    return (
        position.legs[0].side,
        [
            (rule.id, rule.then[0].op, rule.when.dir, rule.when.left.params["period"], rule.when.right.params["period"])
            for rule in definition.rules
        ],
    )


def test_long_ema():
    definition = adapt_v1_definition(LONG)
    assert summary(definition) == ("buy", [("enter", "open", "above", 3, 9), ("exit", "close", "below", 3, 9)])


def test_short_ema():
    definition = adapt_v1_definition(SHORT)
    assert summary(definition) == ("sell", [("enter", "open", "below", 3, 9), ("exit", "close", "above", 3, 9)])


def test_legacy_entry_only_makes_defaults_explicit():
    definition = adapt_v1_definition(LEGACY)
    # Legacy defaults (buy / above) are written out, and there is no exit rule.
    assert summary(definition) == ("buy", [("enter", "open", "above", 3, 9)])


def test_legacy_defaults_apply_per_field():
    only_action = {"entry": {**LEGACY["entry"], "action": "sell"}}
    assert summary(adapt_v1_definition(only_action)) == ("sell", [("enter", "open", "above", 3, 9)])
    legacy_exit = {"entry": LEGACY["entry"], "exit": {"type": "ema_crossover", "fast_period": 3, "slow_period": 9}}
    assert summary(adapt_v1_definition(legacy_exit)) == (
        "buy", [("enter", "open", "above", 3, 9), ("exit", "close", "below", 3, 9)]
    )


def test_direction_is_not_tied_to_action():
    odd = {"entry": {**LONG["entry"], "direction": "below"}, "exit": {**LONG["exit"], "direction": "above"}}
    assert summary(adapt_v1_definition(odd)) == ("buy", [("enter", "open", "below", 3, 9), ("exit", "close", "above", 3, 9)])


def test_distinct_exit_periods_preserved():
    config = {"entry": LONG["entry"], "exit": {**LONG["exit"], "fast_period": 5, "slow_period": 20}}
    assert summary(adapt_v1_definition(config))[1][1] == ("exit", "close", "below", 5, 20)


def test_lifted_definition_is_fully_explicit():
    definition = adapt_v1_definition(LONG, timeframe="1d")
    assert definition.timeframe == "1d" and definition.evaluation == "bar_close"
    position = definition.positions[0]
    assert (position.id, position.role, position.hedges) == ("main", "core", None)
    assert position.sizing == PercentOfAllocationSizing(Decimal(100))
    rule = definition.rules[0]
    assert isinstance(rule.when, CrossCondition)
    ema = rule.when.left
    assert (ema.name, ema.version, ema.output, ema.timeframe, ema.source.field) == ("ema", 1, "value", "1d", "close")


def test_load_definition_tags_v1_fill_model():
    loaded = load_definition(LONG)
    assert (loaded.source_schema_version, loaded.fill_model) == (1, "same_bar_close")
    assert loaded.definition == adapt_v1_definition(LONG)


def test_v1_configuration_is_never_mutated():
    for config in (LONG, SHORT, LEGACY):
        snapshot = copy.deepcopy(config)
        load_definition(config)
        assert config == snapshot


def test_v1_percent_sizing_is_not_authorable_through_the_v2_loader():
    stored = adapt_v1_definition(LONG).to_dict()
    with pytest.raises(StrategyDefinitionError) as info:
        load_v2_definition(stored)
    assert [issue.code for issue in info.value.issues] == ["sizing_not_authorable"]
    stored["positions"]["main"]["sizing"] = {"unit": "shares", "value": 10}
    assert load_v2_definition(stored).rules == adapt_v1_definition(LONG).rules


@pytest.mark.parametrize(
    "config",
    [
        [],
        {},
        {"entry": "ema"},
        {"entry": {"type": "rsi", "fast_period": 3, "slow_period": 9}},
        {"entry": {**LEGACY["entry"], "action": "hold"}},
        {"entry": {**LEGACY["entry"], "direction": "sideways"}},
        {"entry": {"type": "ema_crossover", "fast_period": 9, "slow_period": 9}},
        {"entry": {"type": "ema_crossover", "fast_period": 0, "slow_period": 9}},
        {"entry": {"type": "ema_crossover", "fast_period": "x", "slow_period": 9}},
        {"entry": {"type": "ema_crossover", "slow_period": 9}},
        {"entry": LONG["entry"], "exit": {**LONG["exit"], "action": "buy"}},  # exit must be opposite
        {"entry": LONG["entry"], "exit": "ema"},
        {"entry": LONG["entry"], "exit": {**LONG["exit"], "type": "rsi"}},
    ],
)
def test_malformed_v1_is_rejected_cleanly(config):
    with pytest.raises(StrategyDefinitionError) as info:
        load_definition(config)
    assert info.value.issues
    assert info.value.issues[0].code in {"invalid_v1_configuration", "invalid_document"}
