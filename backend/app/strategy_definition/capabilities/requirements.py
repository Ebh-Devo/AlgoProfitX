"""Derive a definition's capability requirements by walking it (spec §12, §15).

Pure and environment-free: this states what the definition *needs*, never what is available.
Prerequisites beyond what is directly visible come from the capability graph.
"""

from typing import Any, Iterator

from app.strategy_definition.capabilities.model import CapabilityRequirements
from app.strategy_definition.schema import (
    AllCondition,
    AnyCondition,
    CompareCondition,
    CrossCondition,
    EdgeCondition,
    IndicatorRef,
    NotCondition,
    StrategyDefinition,
)
from app.strategy_definition.timeframe import is_intraday


def required_capabilities(definition: StrategyDefinition) -> CapabilityRequirements:
    """The capabilities ``definition`` directly requires, deduplicated."""
    names: set[str] = set()
    if is_intraday(definition.timeframe):
        names.add("data.intraday_bars")

    cores = 0
    for position in definition.positions:
        if position.role == "hedge":
            names.add("positions.hedge")
        else:
            cores += 1
        if len(position.legs) > 1:
            names.add("multi_leg.basket")
        for leg in position.legs:
            names.add(f"leg.instrument.{leg.instrument.kind}")
            names.add(f"leg.side.{leg.side}")
            if leg.side == "sell":
                names.add("short_sell")
        if position.risk is not None:
            for name in ("stop_loss", "take_profit"):
                exit_ = getattr(position.risk, name)
                if exit_ is not None:
                    names.add(f"risk.{name}")
                    names.add(f"risk.basis.{exit_.basis.kind}")
    if cores > 1:
        names.add("positions.multiple_core")

    for rule in definition.rules:
        for operation in rule.then:
            names.add(f"op.{operation.op}")
        for ref in _indicators(rule.when):
            names.add(f"indicator.{ref.name}@{ref.version}")
            if is_intraday(ref.timeframe):
                names.add("data.intraday_bars")
    return CapabilityRequirements(names)


def _indicators(node: Any) -> Iterator[IndicatorRef]:
    """Every indicator under a condition or operand, including nested sources."""
    if isinstance(node, (AllCondition, AnyCondition)):
        for child in node.of:
            yield from _indicators(child)
    elif isinstance(node, (NotCondition, EdgeCondition)):
        yield from _indicators(node.of)
    elif isinstance(node, (CompareCondition, CrossCondition)):
        yield from _indicators(node.left)
        yield from _indicators(node.right)
    elif isinstance(node, IndicatorRef):
        yield node
        if node.source is not None:
            yield from _indicators(node.source)
