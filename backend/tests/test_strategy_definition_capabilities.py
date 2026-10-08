from dataclasses import FrozenInstanceError, replace

import pytest

from app.strategy_definition.capabilities import (
    DEFAULT_CAPABILITY_GRAPH,
    CapabilityGraph,
    CapabilityGraphCycleError,
    CapabilityLayer,
    CapabilityRequirements,
    build_capability_graph,
    layer_of,
    required_capabilities,
)
from app.strategy_definition.indicators import IndicatorCatalog, IndicatorSpec, OutputSpec, ParamSpec
from app.strategy_definition.indicators.catalog import DEFAULT_CATALOG
from app.strategy_definition.schema import (
    Amount,
    CompareCondition,
    ConstantOperand,
    RiskDefinition,
)
from tests.strategy_v2_builders import CLOSE, D, ind, leg, long_definition, op, position, rule, stop

LONG = {"leg.instrument.primary", "leg.side.buy", "op.open", "op.close"}


def caps(definition):
    return set(required_capabilities(definition).required)


def with_when(when, **changes):
    return long_definition(
        rules=(rule("enter", when, [op("open")]), rule("exit", when, [op("close")])), **changes
    )


def test_long_and_short_single_leg():
    assert caps(long_definition()) - {"indicator.ema@1"} == LONG
    short = long_definition(positions=(position(legs=[leg(side="sell")]),))
    assert caps(short) - {"indicator.ema@1"} == (LONG - {"leg.side.buy"}) | {"leg.side.sell", "short_sell"}


@pytest.mark.parametrize("name", ["ema", "rsi", "sma"])
def test_indicator_capabilities_are_version_pinned(name):
    cond = CompareCondition("gt", CLOSE, ind(name, 14))
    assert caps(with_when(cond)) == LONG | {f"indicator.{name}@1"}


def test_nested_indicator_sources_are_walked():
    nested = ind("ema", 9, source=ind("rsi", 14))
    assert {"indicator.ema@1", "indicator.rsi@1"} <= caps(with_when(CompareCondition("gt", nested, CLOSE)))


def test_increase_reduce_and_hedge_and_multiple_core():
    definition = long_definition(
        positions=(position(), position("put", "hedge", "main", [leg("put_leg")])),
        rules=(
            rule("a", then=[op("open", "main"), op("open", "put")]),
            rule("b", then=[op("increase", amount=Amount("sizing_unit", D(1)))]),
            rule("c", then=[op("reduce", amount=Amount("fraction_of_open", D("0.5")))]),
        ),
    )
    result = caps(definition)
    assert {"op.open", "op.increase", "op.reduce", "positions.hedge"} <= result
    assert "op.close" not in result and "positions.multiple_core" not in result
    two_core = long_definition(positions=(position(), position("other", legs=[leg("other_leg")])))
    assert "positions.multiple_core" in caps(two_core)
    basket = long_definition(positions=(position(legs=[leg("a"), leg("b")]),))
    assert "multi_leg.basket" in caps(basket)


def test_risk_capabilities():
    both = long_definition(positions=(position(risk=RiskDefinition(stop_loss=stop(), take_profit=stop("5"))),))
    assert {"risk.stop_loss", "risk.take_profit", "risk.basis.leg_price"} <= caps(both)
    only_stop = long_definition(positions=(position(risk=RiskDefinition(stop_loss=stop())),))
    assert "risk.take_profit" not in caps(only_stop)
    assert not any(name.startswith("risk.") for name in caps(long_definition()))


def test_intraday_timeframe_requires_intraday_data():
    assert "data.intraday_bars" not in caps(long_definition())
    assert "data.intraday_bars" in caps(long_definition(timeframe="5m"))
    htf = replace(long_definition(), timeframe="1d", rules=with_when(CompareCondition("gt", CLOSE, ind("ema", 3, "1h"))).rules)
    assert "data.intraday_bars" in caps(htf)


def test_combined_strategy_is_deduplicated_and_ordered():
    cond = CompareCondition("gt", ind("ema", 9), ind("ema", 21))  # ema twice, plus close compare below
    definition = with_when(cond, positions=(position(legs=[leg(side="sell")], risk=RiskDefinition(stop_loss=stop())),))
    requirements = required_capabilities(definition)
    names = requirements.sorted()
    assert names == tuple(sorted(set(names)))
    assert names.count("indicator.ema@1") == 1
    assert requirements == required_capabilities(definition)
    assert isinstance(requirements.required, frozenset)
    with pytest.raises(FrozenInstanceError):
        requirements.required = frozenset()


def test_layers_are_separated():
    definition = long_definition(
        timeframe="5m",
        positions=(position(legs=[leg(side="sell")], risk=RiskDefinition(stop_loss=stop())),),
    )
    by_layer = required_capabilities(definition).by_layer()
    assert set(by_layer) == set(CapabilityLayer)
    assert "indicator.ema@1" in by_layer[CapabilityLayer.IMPLEMENTATION]
    assert "op.open" in by_layer[CapabilityLayer.IMPLEMENTATION]
    assert by_layer[CapabilityLayer.DATA] == ("data.intraday_bars",)
    assert by_layer[CapabilityLayer.ENVIRONMENT] == ("short_sell",)
    assert required_capabilities(definition).to_dict()["environment"] == ["short_sell"]
    assert layer_of("data.session_anchor") is CapabilityLayer.DATA
    assert layer_of("positions.hedge") is CapabilityLayer.ENVIRONMENT
    with pytest.raises(ValueError):
        layer_of("mystery.feature")
    with pytest.raises(ValueError):
        CapabilityRequirements({"mystery.feature"})


def test_transitive_expansion():
    graph = CapabilityGraph(
        {
            "indicator.vwap@1": ["data.intraday_bars", "data.session_anchor"],
            "data.session_anchor": ["data.intraday_bars"],
            "leg.instrument.option": ["resolver.option", "data.option_chain"],
            "resolver.option": ["data.option_prices"],
        }
    )
    expanded = graph.expand(CapabilityRequirements({"indicator.vwap@1", "leg.instrument.option", "op.open"}))
    assert expanded.sorted() == (
        "data.intraday_bars",
        "data.option_chain",
        "data.option_prices",
        "data.session_anchor",
        "indicator.vwap@1",
        "leg.instrument.option",
        "op.open",
        "resolver.option",
    )
    assert graph.expand(expanded) == expanded  # idempotent
    assert graph.prerequisites("op.open") == ()
    assert graph.prerequisites("indicator.vwap@1") == ("data.intraday_bars", "data.session_anchor")


def test_graph_rejects_cycles_and_unknown_names_and_is_immutable():
    with pytest.raises(CapabilityGraphCycleError) as info:
        CapabilityGraph({"op.a": ["op.b"], "op.b": ["op.c"], "op.c": ["op.a"]})
    assert info.value.cycle == ("op.a", "op.b", "op.c", "op.a")
    with pytest.raises(CapabilityGraphCycleError):
        CapabilityGraph({"op.a": ["op.a"]})
    with pytest.raises(ValueError):
        CapabilityGraph({"op.a": ["bogus"]})
    graph = CapabilityGraph({"op.a": ["data.x"]})
    with pytest.raises(AttributeError):
        graph._edges = {}
    with pytest.raises(TypeError):
        graph._edges["op.z"] = ()


def test_catalog_declares_its_own_requirements():
    assert DEFAULT_CAPABILITY_GRAPH.prerequisites("indicator.ema@1") == ()
    catalog = IndicatorCatalog(
        [
            *DEFAULT_CATALOG.all(),
            IndicatorSpec("anchored", 1, (ParamSpec("period", "integer"),), (OutputSpec("value"),), anchor="session"),
        ]
    )
    graph = build_capability_graph(catalog)
    assert graph.prerequisites("indicator.anchored@1") == ("data.intraday_bars", "data.session_anchor")
    cond = CompareCondition("gt", CLOSE, ind("anchored", 5, "5m"))
    required = required_capabilities(with_when(cond, timeframe="5m"))
    assert "data.session_anchor" not in required
    assert "data.session_anchor" in graph.expand(required)


def test_constant_only_condition_adds_no_indicator_capability():
    cond = CompareCondition("gt", ConstantOperand(D(2)), ConstantOperand(D(1)))
    assert caps(with_when(cond)) == LONG
