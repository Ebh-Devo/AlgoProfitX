"""The orchestrator: one completed bar through the whole pipeline (spec §11.3, §14.2).

    pre-bar snapshot -> rules (priority, declaration) -> conflict resolution
      -> order planning -> execution adapter -> ledger

Risk exits would precede the rules in this order; Phase 5 has none, so that stage is absent
rather than stubbed. The runtime holds no market data and no broker: it is handed one bar's
evaluation context and execution bar at a time.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.strategy_definition.evaluator import EvaluationContext
from app.strategy_definition.runtime.conflicts import resolve_conflicts
from app.strategy_definition.runtime.environment import RuntimeEnvironment
from app.strategy_definition.runtime.execution import (
    ExecutionAdapter,
    ExecutionBar,
    ExecutionEvent,
    SimulatedExecutionAdapter,
)
from app.strategy_definition.runtime.intents import OrderIntent
from app.strategy_definition.runtime.ledger import Ledger, LegKey, ledger_specs
from app.strategy_definition.runtime.operations import (
    CandidateOperation,
    DroppedOperation,
    OperationSource,
    SkippedOperation,
)
from app.strategy_definition.runtime.planner import (
    InstrumentResolver,
    OrderPlanner,
    PrimaryInstrumentResolver,
)
from app.strategy_definition.runtime.rules import RuleEngine, RuleResult
from app.strategy_definition.schema import PositionOperation, StrategyDefinition

END_OF_DATA = OperationSource("engine", "end_of_data")


@dataclass(frozen=True)
class BarOutcome:
    """Everything one bar produced, for diagnostics and replay comparison."""

    timestamp: datetime
    results: tuple[RuleResult, ...]
    skipped: tuple[SkippedOperation, ...]
    dropped: tuple[DroppedOperation, ...]
    intents: tuple[OrderIntent, ...]
    events: tuple[ExecutionEvent, ...]


class StrategyRuntime:
    def __init__(
        self,
        definition: StrategyDefinition,
        environment: RuntimeEnvironment,
        *,
        adapter: ExecutionAdapter | None = None,
        resolver: InstrumentResolver | None = None,
    ) -> None:
        self._rules = RuleEngine(definition)
        self.ledger = Ledger(ledger_specs(definition), environment.initial_capital)
        self._planner = OrderPlanner(
            definition,
            strategy_version_id=environment.strategy_version_id,
            allocation=environment.initial_capital,
            resolver=resolver or PrimaryInstrumentResolver(),
        )
        self._adapter = adapter or SimulatedExecutionAdapter(environment.fill_model)
        self._leg_keys: tuple[LegKey, ...] = tuple(
            (position.id, leg.id) for position in definition.positions for leg in position.legs
        )

    def on_bar_close(self, context: EvaluationContext, bar: ExecutionBar) -> BarOutcome:
        """Evaluate completed bar ``t``. Every rule sees the same pre-bar snapshot."""
        snapshot = self.ledger.snapshot()
        evaluation = self._rules.evaluate(context, snapshot)
        resolution = resolve_conflicts(evaluation.candidates)
        intents = self._plan(resolution.accepted, snapshot, bar)
        events = self._execute(intents, bar)
        return BarOutcome(
            bar.timestamp,
            evaluation.results,
            evaluation.skipped,
            resolution.dropped,
            intents,
            events,
        )

    def liquidate(self, bar: ExecutionBar) -> BarOutcome:
        """Close whatever is still held, as an engine-issued ``close`` (not a rule signal)."""
        snapshot = self.ledger.snapshot()
        candidates = tuple(
            CandidateOperation(END_OF_DATA, index, PositionOperation("close", position.position_id), index)
            for index, position in enumerate(snapshot.positions)
            if position.status.value in ("open", "degraded")
        )
        intents = self._plan(candidates, snapshot, bar)
        return BarOutcome(bar.timestamp, (), (), (), intents, self._execute(intents, bar))

    def equity(self, bar: ExecutionBar) -> Decimal:
        """Ledger equity with every held leg marked at the bar close."""
        return self.ledger.equity({key: bar.close for key in self._leg_keys})

    def _plan(
        self,
        candidates: tuple[CandidateOperation, ...],
        snapshot,
        bar: ExecutionBar,
    ) -> tuple[OrderIntent, ...]:
        intents: list[OrderIntent] = []
        for candidate in candidates:
            intents.extend(
                self._planner.plan(
                    candidate,
                    snapshot.position(candidate.position_id),
                    bar_timestamp=bar.timestamp,
                    reference_price=bar.close,
                )
            )
        return tuple(intents)

    def _execute(
        self, intents: tuple[OrderIntent, ...], bar: ExecutionBar
    ) -> tuple[ExecutionEvent, ...]:
        applied: list[ExecutionEvent] = []
        for intent in intents:
            self.ledger.track_order(intent)
            for event in self._adapter.submit(intent, bar):
                self.ledger.apply_event(event)  # the ledger sees events, never the intent
                applied.append(event)
        return tuple(applied)
