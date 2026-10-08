from dataclasses import FrozenInstanceError, replace

import pytest

from app.strategy_definition.capabilities import (
    DEFAULT_CAPABILITY_GRAPH,
    CapabilityGraph,
    CapabilityGraphCycleError,
    CapabilityLayer,
    CapabilityRequirements,
    CapabilitySpec,
    direct_capabilities,
    layer_of,
    required_capabilities,
)
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


def spec(name, *prerequisites):
    return CapabilitySpec(name, frozenset(prerequisites))


VWAP_LIKE = [
    spec("indicator.anchored@1", "data.intraday_bars", "data.session_anchor"),
    spec("data.session_anchor", "data.intraday_bars"),
    spec("leg.instrument.option", "resolver.option", "data.option_chain"),
    spec("resolver.option", "data.option_prices"),
]


def test_transitive_expansion_multi_level():
    graph = CapabilityGraph(VWAP_LIKE)
    expanded = graph.expand(CapabilityRequirements({"indicator.anchored@1", "leg.instrument.option", "op.open"}))
    assert expanded.sorted() == (
        "data.intraday_bars",
        "data.option_chain",
        "data.option_prices",
        "data.session_anchor",
        "indicator.anchored@1",
        "leg.instrument.option",
        "op.open",
        "resolver.option",
    )
    assert graph.expand(expanded) == expanded  # idempotent
    assert graph.prerequisites("op.open") == ()
    assert graph.prerequisites("indicator.anchored@1") == ("data.intraday_bars", "data.session_anchor")
    assert CapabilitySpec("indicator.anchored@1").layer is CapabilityLayer.IMPLEMENTATION


def test_expansion_is_deterministic_and_deduplicated():
    forward, backward = CapabilityGraph(VWAP_LIKE), CapabilityGraph(reversed(VWAP_LIKE))
    seed = CapabilityRequirements({"indicator.anchored@1", "data.session_anchor", "data.intraday_bars"})
    assert forward.expand(seed).sorted() == backward.expand(seed).sorted()
    assert forward.expand(seed).sorted().count("data.intraday_bars") == 1
    assert [forward.expand(seed).sorted() for _ in range(3)] == [forward.expand(seed).sorted()] * 3


def test_graph_rejects_cycles_duplicates_unknown_names_and_is_immutable():
    with pytest.raises(CapabilityGraphCycleError) as info:
        CapabilityGraph([spec("op.a", "op.b"), spec("op.b", "op.c"), spec("op.c", "op.a")])
    assert info.value.cycle == ("op.a", "op.b", "op.c", "op.a")
    with pytest.raises(CapabilityGraphCycleError):
        CapabilityGraph([spec("op.a", "op.a")])
    with pytest.raises(ValueError):
        spec("op.a", "bogus")
    with pytest.raises(ValueError):
        CapabilityGraph([spec("op.a"), spec("op.a", "data.x")])
    graph = CapabilityGraph([spec("op.a", "data.x")])
    with pytest.raises(AttributeError):
        graph._edges = {}
    with pytest.raises(TypeError):
        graph._edges["op.z"] = frozenset()
    with pytest.raises(FrozenInstanceError):
        CapabilitySpec("op.a").name = "op.b"


def test_required_capabilities_is_already_transitive():
    """Callers never need a separate .expand(): the canonical result is the full set."""
    graph = CapabilityGraph(VWAP_LIKE)
    cond = CompareCondition("gt", CLOSE, ind("anchored", 5, "5m"))
    definition = with_when(cond, timeframe="5m")
    required = required_capabilities(definition, graph=graph)
    assert {"indicator.anchored@1", "data.intraday_bars", "data.session_anchor"} <= required.required
    assert required == graph.expand(required)  # nothing left to expand
    provided = {"op.open", "op.close", "leg.instrument.primary", "leg.side.buy", "data.intraday_bars"}
    assert required - provided >= {"data.session_anchor", "indicator.anchored@1"}
    assert (required - required) == frozenset()


def test_direct_and_transitive_remain_distinguishable():
    graph = CapabilityGraph(VWAP_LIKE)
    cond = CompareCondition("gt", CLOSE, ind("anchored", 5, "1d"))
    definition = with_when(cond)
    direct = direct_capabilities(definition)
    assert "data.session_anchor" not in direct
    assert "data.session_anchor" in required_capabilities(definition, graph=graph)
    assert direct.required < required_capabilities(definition, graph=graph).required


def test_default_graph_leaves_ema_rsi_sma_requirements_unchanged():
    for name in ("ema", "rsi", "sma"):
        definition = with_when(CompareCondition("gt", CLOSE, ind(name, 14)))
        assert required_capabilities(definition) == direct_capabilities(definition)


def test_constant_only_condition_adds_no_indicator_capability():
    cond = CompareCondition("gt", ConstantOperand(D(2)), ConstantOperand(D(1)))
    assert caps(with_when(cond)) == LONG
