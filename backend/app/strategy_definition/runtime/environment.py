"""Environment configuration and pre-run validation.

``backtest_configuration`` is *environment* config (capital, fill model), never part of the
definition. This module is the one place the runtime reads it, and the one place a
``CanonicalDefinition`` is gated (layers 2-3 validation + capability check) before a run.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from app.strategy_definition.runtime.capabilities import check_capabilities
from app.strategy_definition.errors import ValidationIssue
from app.strategy_definition.runtime.errors import RuntimeEnvironmentError, RuntimeSetupError
from app.strategy_definition.runtime.execution import SAME_BAR_CLOSE
from app.strategy_definition.schema import CanonicalDefinition, StrategyDefinition
from app.strategy_definition.validation import validate_definition

# The one Layer 3 issue a lifted V1 definition legitimately raises: V1's all-in sizing is
# represented as percent_of_allocation, which is producible by the V1 adapter only (§7.3).
_V1_ADAPTER_ISSUE = "sizing_not_authorable"

# What this runtime can actually execute. The simulated execution adapter fills at the signal
# bar's close only, and the reference market-data provider serves daily candles only.
SUPPORTED_FILL_MODELS = frozenset({SAME_BAR_CLOSE})
SUPPORTED_TIMEFRAMES = frozenset({"1d"})


@dataclass(frozen=True)
class RuntimeEnvironment:
    strategy_version_id: str
    initial_capital: Decimal
    fill_model: str


def validate_canonical(canonical: CanonicalDefinition) -> StrategyDefinition:
    """Layers 2-3 only: raise ``RuntimeSetupError`` listing every semantic error."""
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
    return canonical.definition


def prepare_definition(canonical: CanonicalDefinition) -> StrategyDefinition:
    """Validate (L2, L3) and capability-check a canonical definition; return it if runnable."""
    definition = validate_canonical(canonical)
    check_capabilities(definition)
    return definition


def environment_issues(
    canonical: CanonicalDefinition, backtest_configuration: Mapping[str, Any]
) -> tuple[ValidationIssue, ...]:
    """Every problem with the environment for this definition, without raising.

    A V2 run must state its fill model and timeframe explicitly (no hidden defaults), and both
    must be ones this runtime can execute, so nothing unsupported is ever run silently.
    """
    issues: list[ValidationIssue] = []
    try:
        capital = Decimal(str(backtest_configuration["initial_capital"]))
        capital_ok = capital.is_finite() and capital > 0
    except (InvalidOperation, KeyError, TypeError, ValueError):
        capital_ok = False
    if not capital_ok:
        issues.append(
            ValidationIssue(
                "backtest_configuration.initial_capital",
                "initial_capital_invalid",
                "initial_capital must be a positive number",
            )
        )

    # An explicit fill model wins; otherwise only a lifted V1 document carries one (its
    # same_bar_close environment default). A V2 run must state it: no hidden default.
    fill_model = backtest_configuration.get("fill_model", canonical.fill_model)
    if not isinstance(fill_model, str) or not fill_model:
        issues.append(
            ValidationIssue(
                "backtest_configuration.fill_model",
                "fill_model_required",
                "fill_model is required for a V2 strategy run",
            )
        )
    elif fill_model not in SUPPORTED_FILL_MODELS:
        issues.append(
            ValidationIssue(
                "backtest_configuration.fill_model",
                "fill_model_unsupported",
                f"fill model {fill_model!r} is not supported; "
                f"supported: {', '.join(sorted(SUPPORTED_FILL_MODELS))}",
            )
        )

    is_v2 = canonical.source_schema_version == 2
    definition_timeframe = canonical.definition.timeframe
    timeframe = backtest_configuration.get("timeframe")
    if is_v2 and definition_timeframe not in SUPPORTED_TIMEFRAMES:
        issues.append(
            ValidationIssue(
                "timeframe",
                "timeframe_unsupported",
                f"timeframe {definition_timeframe!r} is not supported; "
                f"supported: {', '.join(sorted(SUPPORTED_TIMEFRAMES))}",
            )
        )
    if is_v2 and timeframe is None:
        issues.append(
            ValidationIssue(
                "backtest_configuration.timeframe",
                "timeframe_required",
                "backtest_configuration.timeframe is required for a V2 strategy run",
            )
        )
    elif timeframe is not None and timeframe != definition_timeframe:
        issues.append(
            ValidationIssue(
                "backtest_configuration.timeframe",
                "timeframe_mismatch",
                f"backtest timeframe {timeframe!r} disagrees with the definition's "
                f"{definition_timeframe!r}",
            )
        )
    return tuple(issues)


def parse_environment(
    canonical: CanonicalDefinition,
    backtest_configuration: Mapping[str, Any],
    strategy_version_id: str,
) -> RuntimeEnvironment:
    issues = environment_issues(canonical, backtest_configuration)
    if issues:
        raise RuntimeEnvironmentError("; ".join(issue.message for issue in issues), issues)
    if not strategy_version_id:
        raise RuntimeEnvironmentError("strategy_version_id is required for deterministic intent ids")
    return RuntimeEnvironment(
        strategy_version_id,
        Decimal(str(backtest_configuration["initial_capital"])),
        backtest_configuration.get("fill_model", canonical.fill_model),
    )
