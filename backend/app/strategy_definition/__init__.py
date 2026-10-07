"""Strategy Definition V2: canonical model, V2 loader/validator and the V1 adapter.

Phase 1 foundation (docs/STRATEGY_DEFINITION_V2.md §23). Pure and not wired into any
service or API: future runtime consumers receive a ``CanonicalDefinition`` and never read raw
V1 or V2 JSON.
"""

from app.strategy_definition.errors import StrategyDefinitionError, ValidationIssue
from app.strategy_definition.loader import load_v2_definition
from app.strategy_definition.loading import detect_schema_version, load_definition
from app.strategy_definition.schema import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    CanonicalDefinition,
    StrategyDefinition,
)
from app.strategy_definition.v1_adapter import adapt_v1_definition

__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "CanonicalDefinition",
    "StrategyDefinition",
    "StrategyDefinitionError",
    "ValidationIssue",
    "adapt_v1_definition",
    "detect_schema_version",
    "load_definition",
    "load_v2_definition",
]
