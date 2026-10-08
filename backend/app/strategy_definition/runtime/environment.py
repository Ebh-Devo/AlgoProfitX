"""Environment configuration and pre-run validation.

``backtest_configuration`` is *environment* config (capital, fill model), never part of the
definition. This module is the one place the runtime reads it, and the one place a
``CanonicalDefinition`` is gated (layers 2-3 validation + capability check) before a run.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.strategy_definition.runtime.capabilities import check_capabilities
from app.strategy_definition.runtime.errors import RuntimeSetupError
from app.strategy_definition.schema import CanonicalDefinition, StrategyDefinition
from app.strategy_definition.validation import validate_definition

# The one Layer 3 issue a lifted V1 definition legitimately raises: V1's all-in sizing is
# represented as percent_of_allocation, which is producible by the V1 adapter only (§7.3).
_V1_ADAPTER_ISSUE = "sizing_not_authorable"


@dataclass(frozen=True)
class RuntimeEnvironment:
    strategy_version_id: str
    initial_capital: Decimal
    fill_model: str


def prepare_definition(canonical: CanonicalDefinition) -> StrategyDefinition:
    """Validate (L2, L3) and capability-check a canonical definition; return it if runnable."""
    issues = validate_definition(canonical.definition)
    errors = tuple(
        issue
        for issue in issues
        if issue.severity == "error"
        and not (canonical.source_schema_version == 1 and issue.code == _V1_ADAPTER_ISSUE)
    )
    if errors:
        raise RuntimeSetupError(
            "invalid strategy definition: "
            + "; ".join(f"{issue.path or '<root>'}: {issue.message}" for issue in errors),
            errors,
        )
    check_capabilities(canonical.definition)
    return canonical.definition


def parse_environment(
    canonical: CanonicalDefinition,
    backtest_configuration: Mapping[str, Any],
    strategy_version_id: str,
) -> RuntimeEnvironment:
    try:
        capital = Decimal(str(backtest_configuration["initial_capital"]))
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise RuntimeSetupError("initial_capital must be a positive number") from exc
    if not capital.is_finite() or capital <= 0:
        raise RuntimeSetupError("initial_capital must be a positive number")

    # An explicit fill model wins; otherwise only a lifted V1 document carries one (its
    # same_bar_close environment default). A V2 run must state it: no hidden default.
    fill_model = backtest_configuration.get("fill_model", canonical.fill_model)
    if not isinstance(fill_model, str) or not fill_model:
        raise RuntimeSetupError("fill_model is required for a V2 strategy run")

    timeframe = backtest_configuration.get("timeframe")
    if timeframe is not None and timeframe != canonical.definition.timeframe:
        raise RuntimeSetupError(
            f"backtest timeframe {timeframe!r} disagrees with the definition's "
            f"{canonical.definition.timeframe!r}"
        )
    if not strategy_version_id:
        raise RuntimeSetupError("strategy_version_id is required for deterministic intent ids")
    return RuntimeEnvironment(strategy_version_id, capital, fill_model)
