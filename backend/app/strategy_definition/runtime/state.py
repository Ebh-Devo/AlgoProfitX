"""Immutable position state as seen by rules and the planner.

A ``RuntimeSnapshot`` is taken from the ledger *before* a bar is evaluated and is never
updated during that bar, so a rule can never observe another rule's same-bar effect.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class PositionStatus(str, Enum):
    """Ledger-derived position status (spec §14.4). Only the ledger can produce ``open``."""

    FLAT = "flat"
    OPENING = "opening"
    OPEN = "open"
    CLOSING = "closing"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class LegSnapshot:
    leg_id: str
    quantity: Decimal  # signed: long > 0, short < 0, flat == 0
    average_entry_price: Decimal | None  # None while flat


@dataclass(frozen=True)
class PositionSnapshot:
    position_id: str
    status: PositionStatus
    legs: tuple[LegSnapshot, ...]

    def leg(self, leg_id: str) -> LegSnapshot:
        for leg in self.legs:
            if leg.leg_id == leg_id:
                return leg
        raise KeyError(leg_id)


@dataclass(frozen=True)
class RuntimeSnapshot:
    positions: tuple[PositionSnapshot, ...]

    def position(self, position_id: str) -> PositionSnapshot:
        for position in self.positions:
            if position.position_id == position_id:
                return position
        raise KeyError(position_id)
