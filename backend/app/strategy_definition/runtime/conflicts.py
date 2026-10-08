"""Deterministic same-bar conflict resolution, per position (spec §11.3).

Highest rank wins (``close > reduce > increase > open``); equal ranks collapse to the first
in evaluation order; after a ``close`` every other operation on that position is dropped.
So a position gets at most one operation per bar and cannot flip-flop.
"""

from dataclasses import dataclass
from typing import Sequence

from app.strategy_definition.runtime.operations import CandidateOperation, DroppedOperation


@dataclass(frozen=True)
class Resolution:
    accepted: tuple[CandidateOperation, ...]  # in evaluation order
    dropped: tuple[DroppedOperation, ...]  # in evaluation order


def resolve_conflicts(candidates: Sequence[CandidateOperation]) -> Resolution:
    ordered = sorted(candidates, key=lambda item: item.order)
    winners: dict[str, CandidateOperation] = {}
    for candidate in ordered:
        current = winners.get(candidate.position_id)
        if current is None or candidate.rank > current.rank:
            winners[candidate.position_id] = candidate
    dropped: list[DroppedOperation] = []
    for candidate in ordered:
        winner = winners[candidate.position_id]
        if candidate is winner:
            continue
        if winner.operation.op == "close":
            reason = "after_close"
        elif candidate.rank < winner.rank:
            reason = "lower_rank"
        else:
            reason = "equal_rank_duplicate"
        dropped.append(DroppedOperation(candidate, reason, winner))
    accepted = tuple(sorted(winners.values(), key=lambda item: item.order))
    return Resolution(accepted, tuple(dropped))
