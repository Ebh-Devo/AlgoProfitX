"""Version detection and the single entry point from a stored configuration."""

from typing import Any, Literal

from app.strategy_definition.errors import StrategyDefinitionError, ValidationIssue
from app.strategy_definition.loader import load_v2_definition
from app.strategy_definition.schema import CanonicalDefinition
from app.strategy_definition.v1_adapter import V1_FILL_MODEL, adapt_v1_definition


def detect_schema_version(configuration: Any) -> Literal[1, 2]:
    """V2 is explicit: the document carries ``schema`` and/or ``schema_version``.

    Anything without either marker is V1. Nothing else is inspected, so a V2 document is
    never guessed from its other fields; a document that carries a marker but is not a valid
    V2 envelope is routed to the V2 loader, which rejects it.
    """
    if not isinstance(configuration, dict):
        raise StrategyDefinitionError(
            [ValidationIssue("", "invalid_document", "a strategy configuration must be an object")]
        )
    if "schema" in configuration or "schema_version" in configuration:
        return 2
    return 1


def load_definition(configuration: Any, *, v1_timeframe: str = "1d") -> CanonicalDefinition:
    """Stored configuration -> canonical definition. Never mutates ``configuration``."""
    if detect_schema_version(configuration) == 2:
        return CanonicalDefinition(load_v2_definition(configuration), source_schema_version=2)
    return CanonicalDefinition(
        adapt_v1_definition(configuration, timeframe=v1_timeframe),
        source_schema_version=1,
        fill_model=V1_FILL_MODEL,
    )
