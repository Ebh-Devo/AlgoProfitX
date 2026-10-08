"""The position state machine: pure functions, no storage.

* ``derive_status`` maps ledger facts (per-leg filled quantity, working orders) to a status.
* ``precondition_violation`` says whether an operation is legal in a status (spec §10.3).

An operation never *sets* a status; only fills change what the ledger holds.
"""

from decimal import Decimal
from typing import AbstractSet, Mapping

from app.strategy_definition.runtime.state import PositionStatus

# Operations that grow exposure vs. shrink it; used to classify working orders.
OPENING_OPS = frozenset({"open", "increase"})
CLOSING_OPS = frozenset({"close", "reduce"})

_RATIO_TOLERANCE = Decimal("1e-12")


def derive_status(
    held: Mapping[str, Decimal],
    ratios: Mapping[str, Decimal],
    working_ops: AbstractSet[str],
) -> PositionStatus:
    """Status from per-leg held quantity, leg ratios and the ops of working orders.

    ``opening``/``closing``: an open/increase (close/reduce) order is still working.
    Otherwise ``flat`` when nothing is held, ``open`` when held quantities match the fixed
    leg ratios, and ``degraded`` when they do not (an incomplete leg set).
    """
    if working_ops & OPENING_OPS:
        return PositionStatus.OPENING
    if working_ops & CLOSING_OPS:
        return PositionStatus.CLOSING
    units = [abs(held[leg]) / ratios[leg] for leg in ratios]
    if all(unit == 0 for unit in units):
        return PositionStatus.FLAT
    if max(units) - min(units) <= _RATIO_TOLERANCE * max(units):
        return PositionStatus.OPEN
    return PositionStatus.DEGRADED


def precondition_violation(status: PositionStatus, op: str) -> str | None:
    """``None`` when ``op`` is legal in ``status``, else the skip reason (spec §10.3).

    ``open`` needs ``flat``; ``close`` needs ``open`` (or ``degraded``); a position that is
    ``opening`` or ``closing`` accepts no new operation. ``increase``/``reduce`` follow the
    ``close`` rule and are reserved for a later phase.
    """
    if status is PositionStatus.OPENING:
        return "already_opening"
    if status is PositionStatus.CLOSING:
        return "already_closing"
    if op == "open":
        if status is PositionStatus.OPEN:
            return "already_open"
        if status is PositionStatus.DEGRADED:
            return "degraded"
        return None
    if op in ("close", "reduce", "increase"):
        return "flat" if status is PositionStatus.FLAT else None
    return "unsupported_operation"
