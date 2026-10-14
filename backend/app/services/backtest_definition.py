"""ORM-free loading of a backtest's persisted strategy definition.

Shared by the SQL backtest path and the Catalyst path. It reads only four attributes, so it accepts the
SQLAlchemy ``Backtest`` model and the plain ``BacktestRecord`` alike and imports no SQLAlchemy.
"""
from __future__ import annotations

import uuid
from typing import Any, Protocol

from app.backtesting.contracts import BacktestExecutionError
from app.strategy_definition.errors import StrategyDefinitionError
from app.strategy_definition.runtime.environment import parse_environment
from app.strategy_definition.runtime.errors import RuntimeEnvironmentError, RuntimeSetupError
from app.strategy_definition.versioning import (
    LoadedDefinition,
    UnsupportedSchemaVersionError,
    load_definition_for_version,
    resolve_schema_version,
)


class VersionedBacktest(Protocol):
    """The attributes ``load_versioned_definition`` reads."""

    @property
    def definition_schema_version(self) -> Any: ...
    @property
    def configuration_snapshot(self) -> Any: ...
    @property
    def backtest_configuration_snapshot(self) -> Any: ...
    @property
    def strategy_version_id(self) -> uuid.UUID: ...


def load_versioned_definition(backtest: VersionedBacktest) -> LoadedDefinition | None:
    """``None`` for V1 (the existing path, untouched); the validated V2 definition otherwise.

    Order: resolve the persisted version, load, schema, semantic, capability, environment.
    Failures are ``BacktestExecutionError`` with a stable code, raised before market data.
    """
    try:
        version = resolve_schema_version(backtest.definition_schema_version)
        if version == 1:
            return None
        loaded = load_definition_for_version(
            version,
            backtest.configuration_snapshot,
            backtest.backtest_configuration_snapshot,
        )
        parse_environment(
            loaded.canonical,
            backtest.backtest_configuration_snapshot,
            str(backtest.strategy_version_id),
        )
    except UnsupportedSchemaVersionError as exc:
        raise BacktestExecutionError(str(exc), "strategy_definition_unsupported_version") from exc
    except StrategyDefinitionError as exc:
        raise BacktestExecutionError(str(exc), "strategy_definition_invalid") from exc
    except RuntimeSetupError as exc:
        codes = {issue.code for issue in exc.issues}
        if isinstance(exc, RuntimeEnvironmentError):
            code = "strategy_environment_invalid"
        elif "capability_missing" in codes:
            code = "strategy_definition_unsupported_capability"
        elif exc.issues:
            code = "strategy_definition_invalid"
        else:
            code = "strategy_environment_invalid"
        raise BacktestExecutionError(str(exc), code) from exc
    return loaded
