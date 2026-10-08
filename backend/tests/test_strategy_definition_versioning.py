"""The versioned definition loader: the persisted version alone selects the path (Phase 6)."""

from types import SimpleNamespace

import pytest

from app.strategy_definition.errors import StrategyDefinitionError
from app.strategy_definition.runtime.errors import RuntimeSetupError
from app.strategy_definition.versioning import (
    UnsupportedSchemaVersionError,
    load_definition_for_version,
    load_strategy_definition,
    resolve_schema_version,
)
from tests.strategy_v2_builders import D, ind, leg, long_definition, op, position, rule
from app.strategy_definition.schema import CrossCondition, SharesSizing

V1_CONFIGURATION = {
    "entry": {"type": "ema_crossover", "action": "buy", "direction": "above", "fast_period": 3, "slow_period": 9},
}
BACKTEST = {"initial_capital": 10000, "fill_model": "same_bar_close"}


def v2_document(**changes) -> dict:
    definition = long_definition(
        positions=(position(legs=[leg()], sizing=SharesSizing(D(5))),),
        rules=(
            rule("enter", CrossCondition("above", ind("ema", 3), ind("ema", 9)), [op("open")]),
            rule("exit", CrossCondition("below", ind("ema", 3), ind("ema", 9)), [op("close")]),
        ),
        **changes,
    )
    return definition.to_dict()


def version(schema_version, configuration, backtest=BACKTEST):
    return SimpleNamespace(
        definition_schema_version=schema_version,
        configuration=configuration,
        backtest_configuration=backtest,
    )


# --- version resolution ------------------------------------------------------------------


def test_v1_resolves_to_the_v1_adapter():
    loaded = load_strategy_definition(version(1, V1_CONFIGURATION))
    assert loaded.schema_version == 1
    assert loaded.canonical.source_schema_version == 1
    assert loaded.canonical.fill_model == "same_bar_close"


def test_v2_resolves_to_the_v2_loader():
    loaded = load_strategy_definition(version(2, v2_document()))
    assert loaded.schema_version == 2
    assert loaded.canonical.source_schema_version == 2
    assert loaded.canonical.fill_model is None


def test_a_legacy_record_without_a_version_is_v1():
    legacy = SimpleNamespace(configuration=V1_CONFIGURATION, backtest_configuration={})
    assert load_strategy_definition(legacy).schema_version == 1
    assert load_strategy_definition(version(None, V1_CONFIGURATION)).schema_version == 1
    assert resolve_schema_version(None) == 1


@pytest.mark.parametrize("bad", [0, 3, -1, 99, True, False, "2", "1", 2.0, [], {}])
def test_unsupported_versions_are_rejected_deterministically(bad):
    with pytest.raises(UnsupportedSchemaVersionError) as caught:
        load_strategy_definition(version(bad, V1_CONFIGURATION))
    assert isinstance(caught.value, StrategyDefinitionError)
    assert caught.value.issues[0].code == "unsupported_schema_version"


# --- the persisted version is authoritative; JSON shape is never consulted ----------------


def test_a_v2_document_stored_as_version_1_is_judged_by_the_v1_adapter_only():
    with pytest.raises(StrategyDefinitionError) as caught:
        load_strategy_definition(version(1, v2_document()))
    assert caught.value.issues[0].code == "invalid_v1_configuration"


def test_a_v1_document_stored_as_version_2_fails_the_v2_loader_without_fallback():
    with pytest.raises(StrategyDefinitionError) as caught:
        load_strategy_definition(version(2, V1_CONFIGURATION))
    assert not isinstance(caught.value, UnsupportedSchemaVersionError)
    assert {issue.path for issue in caught.value.issues} >= {"schema"}


# --- validation layers --------------------------------------------------------------------


def test_malformed_v2_fails_at_the_schema_layer():
    for document in ({}, {"schema_version": 2}, [], None, "x"):
        with pytest.raises(StrategyDefinitionError):
            load_strategy_definition(version(2, document))


def test_semantically_invalid_v2_fails_before_any_runtime():
    only_close = long_definition(
        rules=(rule("x", CrossCondition("below", ind("ema", 3), ind("ema", 9)), [op("close")]),)
    ).to_dict()
    with pytest.raises(RuntimeSetupError) as caught:
        load_strategy_definition(version(2, only_close))
    assert caught.value.issues
    assert not any(issue.code == "capability_missing" for issue in caught.value.issues)


def test_a_capability_the_runtime_lacks_is_refused():
    two_legs = long_definition(positions=(position(legs=[leg("a"), leg("b")]),)).to_dict()
    with pytest.raises(RuntimeSetupError) as caught:
        load_strategy_definition(version(2, two_legs))
    assert {issue.code for issue in caught.value.issues} == {"capability_missing"}


def test_creation_time_validation_skips_the_capability_check_only():
    two_legs = long_definition(positions=(position(legs=[leg("a"), leg("b")]),)).to_dict()
    loaded = load_definition_for_version(2, two_legs, BACKTEST, check_runtime_capabilities=False)
    assert loaded.schema_version == 2
    with pytest.raises(StrategyDefinitionError):
        load_definition_for_version(2, {"schema_version": 2}, BACKTEST, check_runtime_capabilities=False)


def test_loading_never_mutates_the_stored_document():
    document = v2_document()
    snapshot = repr(document)
    load_strategy_definition(version(2, document))
    assert repr(document) == snapshot
    v1 = dict(V1_CONFIGURATION)
    load_strategy_definition(version(1, v1))
    assert v1 == V1_CONFIGURATION
