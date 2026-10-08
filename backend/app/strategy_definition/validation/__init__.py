"""Layers 2 and 3 of the V2 validation architecture (spec §12): semantic and position.

Both operate on a typed ``StrategyDefinition`` (never raw JSON) and are environment-free.
"""

from app.strategy_definition.errors import ValidationIssue
from app.strategy_definition.indicators import DEFAULT_CATALOG, IndicatorCatalog
from app.strategy_definition.schema import StrategyDefinition
from app.strategy_definition.validation.position import validate_position_semantics
from app.strategy_definition.validation.semantic import validate_semantics


def validate_definition(
    definition: StrategyDefinition, *, catalog: IndicatorCatalog = DEFAULT_CATALOG
) -> tuple[ValidationIssue, ...]:
    """Layer 2 then Layer 3 issues. A definition is valid when none has severity ``error``."""
    return validate_semantics(definition, catalog=catalog) + validate_position_semantics(definition)


__all__ = ["validate_definition", "validate_position_semantics", "validate_semantics"]
