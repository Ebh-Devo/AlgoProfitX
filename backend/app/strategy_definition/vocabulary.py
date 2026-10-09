"""The *runnable* V2 authoring vocabulary, derived from what the runtime actually provides.

There is no second registry here: capabilities come from ``RUNTIME_CAPABILITIES``, indicators from
``DEFAULT_CATALOG`` filtered by those capabilities, and the environment limits from
``environment``. Adding a capability to the runtime widens this vocabulary; removing one narrows it.
Structural vocabulary (condition kinds, fields) is read off the typed schema.
"""

from typing import Any, get_args, get_type_hints

from app.strategy_definition.indicators import DEFAULT_CATALOG
from app.strategy_definition.runtime.capabilities import RUNTIME_CAPABILITIES
from app.strategy_definition.runtime.environment import SUPPORTED_FILL_MODELS, SUPPORTED_TIMEFRAMES
from app.strategy_definition.schema import (
    CompareCondition,
    CrossCondition,
    EdgeCondition,
    PriceOperand,
    SharesSizing,
)

CONDITION_KINDS = ("compare", "cross", "all", "any", "not", "edge")
OPERAND_KINDS = ("price", "constant", "indicator")
EVALUATION_MODES = ("bar_close",)
# A runtime indicator reads a price series; volume is not a valid indicator source.
INDICATOR_SOURCE_FIELDS = ("open", "high", "low", "close")


# Schema-valid operators the semantic layer only accepts between two constants (exact equality on
# a price/indicator series is rejected, spec §8.2). A constant-vs-constant comparison never
# changes, so it is not a usable authoring choice and is not advertised.
CONSTANT_ONLY_COMPARE_OPS = frozenset({"eq"})


def _literal(cls: type, name: str) -> tuple[str, ...]:
    return tuple(get_args(get_type_hints(cls)[name]))


def _suffixes(prefix: str) -> list[str]:
    return sorted(name[len(prefix):] for name in RUNTIME_CAPABILITIES if name.startswith(prefix))


def runnable_vocabulary() -> dict[str, Any]:
    provided = RUNTIME_CAPABILITIES
    indicators = [
        {
            "key": spec.key,
            "name": spec.name,
            "version": spec.version,
            "params": [
                {
                    "name": param.name,
                    "type": param.type,
                    "required": param.required,
                    "minimum": param.minimum,
                    "maximum": param.maximum,
                }
                for param in spec.params
            ],
            "outputs": [output.name for output in spec.outputs],
        }
        for spec in DEFAULT_CATALOG.all()
        if f"indicator.{spec.key}" in provided
    ]
    return {
        "definition_schema_version": 2,
        "timeframes": sorted(SUPPORTED_TIMEFRAMES),
        "evaluation_modes": list(EVALUATION_MODES),
        "fill_models": sorted(SUPPORTED_FILL_MODELS),
        "position": {
            "roles": ["core"] + (["hedge"] if "positions.hedge" in provided else []),
            "max_core_positions": None if "positions.multiple_core" in provided else 1,
            "max_legs_per_position": None if "multi_leg.basket" in provided else 1,
            "instrument_kinds": _suffixes("leg.instrument."),
            "leg_sides": _suffixes("leg.side."),
            "sizing_units": list(_literal(SharesSizing, "unit")),
        },
        "operations": _suffixes("op."),
        "condition_kinds": list(CONDITION_KINDS),
        "compare_operators": [
            op for op in _literal(CompareCondition, "op") if op not in CONSTANT_ONLY_COMPARE_OPS
        ],
        "cross_directions": list(_literal(CrossCondition, "dir")),
        "edge_directions": list(_literal(EdgeCondition, "dir")),
        "operand_kinds": list(OPERAND_KINDS),
        "price_fields": list(_literal(PriceOperand, "field")),
        "indicator_source_fields": list(INDICATOR_SOURCE_FIELDS),
        "indicators": indicators,
        "supports_rule_limits": "rule.limits" in provided,
        "supports_risk_rules": "risk.stop_loss" in provided or "risk.take_profit" in provided,
        "capabilities": sorted(provided),
    }
