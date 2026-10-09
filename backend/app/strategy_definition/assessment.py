"""Side-effect-free assessment of a V2 draft: the one place that answers "is this usable?".

It composes the existing validators in their documented order and never duplicates their rules:

    schema (loader)  ->  semantic  ->  position  ->  capability  ->  environment

``savable``  no schema/semantic/position error: the document is a well-formed definition.
``runnable`` ``savable`` *and* every required capability is provided *and* the environment
             (fill model, timeframe, capital) is one the runtime can execute.
``valid``    no error-severity issue in any layer (warnings never fail it).

It reads no database and no market data; the same checks gate execution, so a draft reported
runnable here passes the pre-run gate.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from app.strategy_definition.capabilities import required_capabilities
from app.strategy_definition.errors import StrategyDefinitionError, ValidationIssue
from app.strategy_definition.indicators import DEFAULT_CATALOG
from app.strategy_definition.loader import load_v2_definition
from app.strategy_definition.runtime.capabilities import capability_issues
from app.strategy_definition.runtime.environment import environment_issues
from app.strategy_definition.schema import CanonicalDefinition
from app.strategy_definition.validation import validate_position_semantics, validate_semantics

LAYER_SCHEMA = "schema"
LAYER_SEMANTIC = "semantic"
LAYER_POSITION = "position"
LAYER_CAPABILITY = "capability"
LAYER_ENVIRONMENT = "environment"


@dataclass(frozen=True)
class LayeredIssue:
    issue: ValidationIssue
    layer: str


@dataclass(frozen=True)
class DefinitionAssessment:
    issues: tuple[LayeredIssue, ...]
    required_capabilities: tuple[str, ...]
    unsupported_capabilities: tuple[str, ...]

    @property
    def errors(self) -> tuple[LayeredIssue, ...]:
        return tuple(item for item in self.issues if item.issue.severity == "error")

    @property
    def savable(self) -> bool:
        return not any(
            item.layer in (LAYER_SCHEMA, LAYER_SEMANTIC, LAYER_POSITION) for item in self.errors
        )

    @property
    def runnable(self) -> bool:
        return self.savable and not self.errors

    @property
    def valid(self) -> bool:
        return not self.errors


def assess_v2_definition(
    configuration: Any, backtest_configuration: Mapping[str, Any]
) -> DefinitionAssessment:
    """Assess a V2 document and its environment. Pure: nothing is persisted or fetched."""
    try:
        canonical = CanonicalDefinition(load_v2_definition(configuration), source_schema_version=2)
    except StrategyDefinitionError as exc:
        return DefinitionAssessment(
            tuple(LayeredIssue(issue, LAYER_SCHEMA) for issue in exc.issues), (), ()
        )

    definition = canonical.definition
    issues = [
        *(LayeredIssue(i, LAYER_SEMANTIC) for i in validate_semantics(definition, catalog=DEFAULT_CATALOG)),
        *(LayeredIssue(i, LAYER_POSITION) for i in validate_position_semantics(definition)),
    ]

    required = required_capabilities(definition)
    missing, capability_problems = capability_issues(definition)
    issues.extend(LayeredIssue(i, LAYER_CAPABILITY) for i in capability_problems)
    issues.extend(
        LayeredIssue(i, LAYER_ENVIRONMENT) for i in environment_issues(canonical, backtest_configuration)
    )
    return DefinitionAssessment(tuple(issues), required.sorted(), missing)
