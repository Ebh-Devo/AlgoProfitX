"""What this runtime provides, checked against what a definition requires (spec §12 layer 4).

Phase 5 is single position, single leg, ``open``/``close``, ``bar_close``, ``ema@1``. Anything
else a definition requires (``op.increase``, ``risk.stop_loss``, ``multi_leg.basket``, ...)
is reported as missing and the run is refused before any candle is processed.
"""

from app.strategy_definition.capabilities import (
    CapabilityLayer,
    layer_of,
    required_capabilities,
)
from app.strategy_definition.errors import ValidationIssue
from app.strategy_definition.runtime.errors import RuntimeSetupError
from app.strategy_definition.schema import StrategyDefinition

RUNTIME_CAPABILITIES = frozenset(
    {
        "op.open",
        "op.close",
        "leg.instrument.primary",
        "leg.side.buy",
        "leg.side.sell",
        "short_sell",
        "indicator.ema@1",
    }
)


def check_capabilities(
    definition: StrategyDefinition, provided: frozenset[str] = RUNTIME_CAPABILITIES
) -> None:
    """Raise ``RuntimeSetupError`` naming every unmet requirement, grouped by layer."""
    missing = required_capabilities(definition) - provided
    if not missing:
        return
    issues = tuple(
        ValidationIssue("", "capability_missing", f"{layer_of(name).value}: {name}")
        for layer in CapabilityLayer
        for name in sorted(missing)
        if layer_of(name) is layer
    )
    raise RuntimeSetupError(
        "the definition needs capabilities this runtime does not provide: "
        + ", ".join(sorted(missing)),
        issues,
    )
