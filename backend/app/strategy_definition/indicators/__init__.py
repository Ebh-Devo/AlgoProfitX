"""Indicator catalog (docs/STRATEGY_DEFINITION_V2.md §9.3): metadata and validation only.

The catalog says which ``name@version`` indicators are valid V2 references, with which
parameters and outputs. It performs no calculation and touches no environment.
"""

from app.strategy_definition.indicators.catalog import (
    DEFAULT_CATALOG,
    IndicatorCatalog,
    UnknownIndicatorError,
    UnknownIndicatorVersionError,
)
from app.strategy_definition.indicators.spec import (
    IndicatorSpec,
    OutputSpec,
    ParamSpec,
    ParamViolation,
)

__all__ = [
    "DEFAULT_CATALOG",
    "IndicatorCatalog",
    "IndicatorSpec",
    "OutputSpec",
    "ParamSpec",
    "ParamViolation",
    "UnknownIndicatorError",
    "UnknownIndicatorVersionError",
]
