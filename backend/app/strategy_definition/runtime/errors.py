"""Structured runtime errors (Phase 5).

Each class is a distinct failure *kind*; none of them is ever converted into a FALSE
condition or swallowed. An execution rejection is deliberately *not* here: per spec §14.4 a
reject is a first-class ``rejected`` event, not an exception.
"""

from app.strategy_definition.errors import ValidationIssue


class StrategyRuntimeError(Exception):
    """Base class for every failure raised by the strategy runtime."""


class RuntimeSetupError(StrategyRuntimeError):
    """The definition or environment cannot be run: invalid, or beyond this runtime's
    capabilities. Raised before any candle is processed."""

    def __init__(self, message: str, issues: tuple[ValidationIssue, ...] = ()):
        super().__init__(message)
        self.issues = tuple(issues)


class RuntimeEnvironmentError(RuntimeSetupError):
    """The environment (``backtest_configuration``) cannot be run: bad capital, a fill model or
    timeframe this runtime does not support. Distinguished from a definition problem so callers
    can report ``strategy_environment_invalid``."""


class UnsupportedOperationError(StrategyRuntimeError):
    """A position operation that is reserved but not implemented (``increase``, ``reduce``)."""


class RuntimeDataError(StrategyRuntimeError):
    """The market data handed to the runtime is unusable (empty, unordered, naive times)."""


class ExecutionError(StrategyRuntimeError):
    """An execution adapter broke its contract (e.g. an unsupported intent or fill model)."""


class LedgerInconsistencyError(StrategyRuntimeError):
    """An event stream that cannot be applied: unknown intent, illegal lifecycle step,
    over-fill, or a conflicting duplicate. Never silently repaired."""
