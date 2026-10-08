"""The authoritative service boundary: persisted StrategyVersion -> validated canonical definition.

    persisted ``definition_schema_version``   (the only selector; the JSON is never sniffed)
        1 (or a legacy record without one) -> V1 compatibility adapter
        2                                  -> V2 loader
        anything else                      -> ``UnsupportedSchemaVersionError``
    then, in this order, for either version:
        JSON/schema load  ->  semantic + position validation  ->  capability check

Every service that needs a definition goes through here, so no service interprets V1 or V2 JSON
itself. Errors are deterministic and typed:

  * ``UnsupportedSchemaVersionError`` (a ``StrategyDefinitionError``): the version is not 1 or 2.
  * ``StrategyDefinitionError``: the document is malformed for its version (schema layer).
  * ``RuntimeSetupError``: the document loads but is semantically invalid, or needs a capability
    the runtime lacks. ``.issues`` carries the structured detail.

Nothing here touches market data: all of it runs before any candle is read.
"""

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from app.strategy_definition.errors import StrategyDefinitionError, ValidationIssue
from app.strategy_definition.loader import load_v2_definition
from app.strategy_definition.runtime.environment import prepare_definition, validate_canonical
from app.strategy_definition.schema import CanonicalDefinition, StrategyDefinition
from app.strategy_definition.v1_adapter import V1_FILL_MODEL, adapt_v1_definition

SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1, 2)
# A record that predates the persisted field (an unflushed/legacy object with no value) is V1.
# Physical rows are backfilled to 1 by the column's server default, so this is the same rule.
LEGACY_SCHEMA_VERSION = 1


class UnsupportedSchemaVersionError(StrategyDefinitionError):
    def __init__(self, version: object):
        super().__init__(
            [
                ValidationIssue(
                    "definition_schema_version",
                    "unsupported_schema_version",
                    f"unsupported definition schema version {version!r}; "
                    f"supported versions are {list(SUPPORTED_SCHEMA_VERSIONS)}",
                )
            ]
        )
        self.version = version


@dataclass(frozen=True)
class LoadedDefinition:
    """A definition that has passed every pre-run gate and may be handed to the runtime."""

    canonical: CanonicalDefinition
    definition: StrategyDefinition
    schema_version: Literal[1, 2]


def resolve_schema_version(value: object) -> Literal[1, 2]:
    """``None`` -> 1 (legacy). Exactly ``1`` or ``2`` (not ``True``, not ``"2"``) -> itself."""
    if value is None:
        return LEGACY_SCHEMA_VERSION  # type: ignore[return-value]
    if isinstance(value, bool) or not isinstance(value, int) or value not in SUPPORTED_SCHEMA_VERSIONS:
        raise UnsupportedSchemaVersionError(value)
    return value  # type: ignore[return-value]


def load_canonical_definition(
    schema_version: object,
    configuration: Any,
    backtest_configuration: Mapping[str, Any] | None = None,
) -> CanonicalDefinition:
    """Layer 1 only: select the loader by the persisted version and build the canonical form."""
    version = resolve_schema_version(schema_version)
    if version == 1:
        timeframe = (backtest_configuration or {}).get("timeframe", "1d")
        return CanonicalDefinition(
            adapt_v1_definition(configuration, timeframe=timeframe),
            source_schema_version=1,
            fill_model=V1_FILL_MODEL,
        )
    return CanonicalDefinition(load_v2_definition(configuration), source_schema_version=2)


def load_definition_for_version(
    schema_version: object,
    configuration: Any,
    backtest_configuration: Mapping[str, Any] | None = None,
    *,
    check_runtime_capabilities: bool = True,
) -> LoadedDefinition:
    """Schema -> semantic -> (optionally) capability validation, for the given persisted version."""
    canonical = load_canonical_definition(schema_version, configuration, backtest_configuration)
    definition = (
        prepare_definition(canonical)  # semantic validation, then capabilities
        if check_runtime_capabilities
        else validate_canonical(canonical)  # creation-time: valid, but not necessarily runnable
    )
    return LoadedDefinition(canonical, definition, canonical.source_schema_version)


def load_strategy_definition(strategy_version: Any) -> LoadedDefinition:
    """The canonical entry point for a persisted ``StrategyVersion`` (or anything shaped like one)."""
    return load_definition_for_version(
        getattr(strategy_version, "definition_schema_version", None),
        strategy_version.configuration,
        strategy_version.backtest_configuration,
    )
