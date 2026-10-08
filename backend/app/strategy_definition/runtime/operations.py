"""Position operations as produced by the rule engine, before any order exists."""

from dataclasses import dataclass
from typing import Literal

from app.strategy_definition.schema import PositionOperation

# close > reduce > increase > open (spec §11.3). Later phases add ops by adding ranks.
OP_RANK: dict[str, int] = {"open": 1, "increase": 2, "reduce": 3, "close": 4}


@dataclass(frozen=True)
class OperationSource:
    """What produced an operation: a rule, a risk exit (later), or the engine itself."""

    kind: Literal["rule", "risk", "engine"]
    id: str

    @property
    def reason(self) -> str:
        """Exit-reason text: ``rule:<id>`` for rules, the bare id for risk/engine sources."""
        return f"rule:{self.id}" if self.kind == "rule" else self.id


@dataclass(frozen=True)
class CandidateOperation:
    """A rule-fired operation in evaluation order, with the identity inputs it needs."""

    source: OperationSource
    op_index: int  # index within the rule's ``then`` list
    operation: PositionOperation
    order: int  # global evaluation order: (priority, declaration), then op_index

    @property
    def position_id(self) -> str:
        return self.operation.position

    @property
    def rank(self) -> int:
        return OP_RANK[self.operation.op]


@dataclass(frozen=True)
class SkippedOperation:
    """An operation not run because its precondition failed (spec §10.3). Recorded."""

    source: OperationSource
    operation: PositionOperation
    reason: str


@dataclass(frozen=True)
class DroppedOperation:
    """An operation lost a same-bar conflict on its position (spec §11.3). Recorded."""

    candidate: CandidateOperation
    reason: str
    winner: CandidateOperation
