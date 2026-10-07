"""Indicator catalog (Strategy V2 Phase 2): lookup, parameter/output validation, loader wiring."""

import dataclasses

import pytest

from app.strategy_definition import StrategyDefinitionError, load_definition, load_v2_definition
from app.strategy_definition.indicators import (
    DEFAULT_CATALOG,
    IndicatorCatalog,
    IndicatorSpec,
    UnknownIndicatorError,
    UnknownIndicatorVersionError,
)
from tests.test_strategy_definition_v2 import document, ema, rsi

# --- catalog ------------------------------------------------------------------------------


def test_registered_indicators_are_retrievable_and_versioned():
    for name in ("ema", "rsi"):
        spec = DEFAULT_CATALOG.get(name, 1)
        assert (spec.name, spec.version, spec.key) == (name, 1, f"{name}@1")
        assert DEFAULT_CATALOG.has(name, 1)
        assert [o.name for o in spec.outputs] == ["value"]
        (period,) = spec.params
        assert (period.name, period.type, period.required, period.minimum) == ("period", "integer", True, 1)


def test_only_needed_indicators_are_registered():
    assert [spec.key for spec in DEFAULT_CATALOG.all()] == ["ema@1", "rsi@1"]


def test_lookup_and_enumeration_are_deterministic():
    assert DEFAULT_CATALOG.get("ema", 1) is DEFAULT_CATALOG.get("ema", 1)
    assert DEFAULT_CATALOG.all() == DEFAULT_CATALOG.all()
    shuffled = IndicatorCatalog(reversed(DEFAULT_CATALOG.all()))
    assert shuffled.all() == DEFAULT_CATALOG.all()


def test_unknown_indicator_and_version_fail_without_fallback():
    with pytest.raises(UnknownIndicatorError):
        DEFAULT_CATALOG.get("macd", 1)
    with pytest.raises(UnknownIndicatorVersionError) as info:
        DEFAULT_CATALOG.get("ema", 2)
    assert info.value.available == (1,)
    assert not DEFAULT_CATALOG.has("ema", 2) and not DEFAULT_CATALOG.has("macd", 1)


def test_duplicate_registration_rejected():
    spec = DEFAULT_CATALOG.get("ema", 1)
    with pytest.raises(ValueError):
        IndicatorCatalog([spec, spec])


def test_catalog_cannot_be_mutated_through_returned_objects():
    spec = DEFAULT_CATALOG.get("ema", 1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.version = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.params[0].minimum = 0  # type: ignore[misc]
    assert isinstance(spec.params, tuple) and isinstance(spec.outputs, tuple)
    assert isinstance(DEFAULT_CATALOG.all(), tuple)
    assert isinstance(spec, IndicatorSpec)


# --- parameters and outputs ---------------------------------------------------------------


def violations(params):
    return {(v.param, v.code) for v in DEFAULT_CATALOG.get("ema", 1).validate_params(params)}


def test_valid_params_accepted():
    assert violations({"period": 1}) == set()
    assert violations({"period": 5000}) == set()


@pytest.mark.parametrize("value", [1.5, 3.0, "3", None, True])
def test_invalid_param_type_rejected(value):
    assert violations({"period": value}) == {("period", "invalid_param_type")}


@pytest.mark.parametrize("value", [0, -1, 5001])
def test_param_out_of_range_rejected(value):
    assert violations({"period": value}) == {("period", "param_out_of_range")}


def test_unknown_and_missing_params_rejected():
    assert violations({"period": 3, "window": 4}) == {("window", "unknown_param")}
    assert violations({}) == {("period", "missing_param")}


def test_outputs():
    spec = DEFAULT_CATALOG.get("rsi", 1)
    assert spec.has_output("value") and not spec.has_output("upper")


# --- loader integration -------------------------------------------------------------------


def with_left(indicator):
    doc = document()
    doc["rules"][0]["when"] = {
        "kind": "compare", "op": "gt", "left": indicator, "right": {"kind": "constant", "value": 1},
    }
    return doc


def load_codes(indicator):
    with pytest.raises(StrategyDefinitionError) as info:
        load_v2_definition(with_left(indicator))
    return {(i.path, i.code) for i in info.value.issues}


LEFT = "rules[0].when.left"


def test_valid_indicator_reference_loads():
    definition = load_v2_definition(with_left(rsi(14)))
    assert definition.rules[0].when.left.name == "rsi"
    assert load_definition(document()).source_schema_version == 2


def test_unknown_indicator_rejected():
    assert load_codes({**ema(3), "name": "made_up_indicator"}) == {(f"{LEFT}.name", "unknown_indicator")}


def test_unknown_version_rejected():
    assert load_codes({**ema(3), "version": 2}) == {(f"{LEFT}.version", "unknown_indicator_version")}


def test_invalid_params_rejected():
    assert load_codes({**ema(3), "params": {}}) == {(f"{LEFT}.params.period", "missing_param")}
    assert load_codes({**ema(3), "params": {"period": 0}}) == {(f"{LEFT}.params.period", "param_out_of_range")}
    assert load_codes({**ema(3), "params": {"period": 2.5}}) == {(f"{LEFT}.params.period", "invalid_param_type")}
    assert load_codes({**ema(3), "params": {"period": 3, "x": 1}}) == {(f"{LEFT}.params.x", "unknown_param")}


def test_invalid_output_rejected():
    assert load_codes({**ema(3), "output": "upper"}) == {(f"{LEFT}.output", "unknown_output")}


def test_nested_source_is_validated():
    doc = with_left({**ema(3), "source": {**rsi(14), "version": 9}})
    with pytest.raises(StrategyDefinitionError) as info:
        load_v2_definition(doc)
    assert {(i.path, i.code) for i in info.value.issues} == {
        (f"{LEFT}.source.version", "unknown_indicator_version")
    }


def test_loader_uses_supplied_catalog():
    empty = IndicatorCatalog([])
    with pytest.raises(StrategyDefinitionError):
        load_v2_definition(document(), catalog=empty)


def test_v1_adapter_still_loads_against_catalog():
    loaded = load_definition({"entry": {"type": "ema_crossover", "fast_period": 5, "slow_period": 20}})
    assert loaded.source_schema_version == 1
    # The adapter's indicator refs are valid catalog references.
    assert DEFAULT_CATALOG.has("ema", 1)
