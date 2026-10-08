"""Strategy V2 runtime, Phase 5 (docs/STRATEGY_DEFINITION_V2.md §14).

Single position, single leg, ``open``/``close``, ``bar_close``, simulated ``same_bar_close``
execution. Pure and broker-independent; not wired into any service or API.

    rules -> operations -> conflicts -> planner -> OrderIntent
          -> execution adapter -> ExecutionEvent -> ledger -> status / P&L / equity
"""

from app.strategy_definition.runtime.engine import RuntimeRun, StrategyRuntimeEngine
from app.strategy_definition.runtime.errors import (
    ExecutionError,
    LedgerInconsistencyError,
    RuntimeDataError,
    RuntimeSetupError,
    StrategyRuntimeError,
    UnsupportedOperationError,
)
from app.strategy_definition.runtime.execution import (
    EventType,
    ExecutionAdapter,
    ExecutionEvent,
    SimulatedExecutionAdapter,
)
from app.strategy_definition.runtime.intents import OrderIntent, make_intent_id
from app.strategy_definition.runtime.ledger import Ledger
from app.strategy_definition.runtime.state import PositionStatus

__all__ = [
    "EventType",
    "ExecutionAdapter",
    "ExecutionError",
    "ExecutionEvent",
    "Ledger",
    "LedgerInconsistencyError",
    "OrderIntent",
    "PositionStatus",
    "RuntimeDataError",
    "RuntimeRun",
    "RuntimeSetupError",
    "SimulatedExecutionAdapter",
    "StrategyRuntimeEngine",
    "StrategyRuntimeError",
    "UnsupportedOperationError",
    "make_intent_id",
]
