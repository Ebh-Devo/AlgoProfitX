"""The execution seam (spec §14.4): order intents in, execution events out.

Every environment (simulated, paper, live) implements ``ExecutionAdapter``; only the producer
of events differs. The ledger consumes the events, never the intents. ``filled_qty`` is the
quantity filled *by that event* (incremental), ``price`` the fill price of that event.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Protocol

from app.strategy_definition.runtime.errors import ExecutionError
from app.strategy_definition.runtime.intents import OrderIntent

SAME_BAR_CLOSE = "same_bar_close"


class EventType(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ExecutionEvent:
    intent_id: str
    event_seq: int  # per intent, strictly increasing; the ledger de-duplicates on (intent_id, seq)
    type: EventType
    ts: datetime  # UTC
    filled_qty: Decimal | None = None
    price: Decimal | None = None
    fees: Decimal = Decimal(0)
    reason: str | None = None
    attempt: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "event_seq": self.event_seq,
            "type": self.type.value,
            "ts": self.ts.astimezone(timezone.utc).isoformat(),
            "filled_qty": None if self.filled_qty is None else str(self.filled_qty),
            "price": None if self.price is None else str(self.price),
            "fees": str(self.fees),
            "reason": self.reason,
            "attempt": self.attempt,
        }


@dataclass(frozen=True)
class ExecutionBar:
    """The bar an order is exposed to: what a simulated fill may use."""

    timestamp: datetime
    close: Decimal


class ExecutionAdapter(Protocol):
    def submit(self, intent: OrderIntent, bar: ExecutionBar) -> tuple[ExecutionEvent, ...]:
        """Submit an intent. Repeating an ``intent_id`` must return the same order's events."""
        ...


# --- Simulated execution -------------------------------------------------------------------


@dataclass(frozen=True)
class CompleteFill:
    """Default simulated outcome: accepted, then filled in full."""


@dataclass(frozen=True)
class Reject:
    reason: str


@dataclass(frozen=True)
class PartialFill:
    """Accepted, partially filled, then the remainder ends (``expired`` or ``cancelled``)."""

    quantity: Decimal
    then: EventType = EventType.EXPIRED


SimulatedOutcome = CompleteFill | Reject | PartialFill


class SimulatedExecutionAdapter:
    """Backtest execution. ``same_bar_close`` fills at the signal bar's close, at its timestamp.

    ``next_bar_open`` is part of the spec but not implemented here, and is refused rather
    than approximated. ``behavior`` decides each order's outcome (default: complete fill).
    """

    def __init__(
        self,
        fill_model: str = SAME_BAR_CLOSE,
        *,
        behavior: Callable[[OrderIntent], SimulatedOutcome] | None = None,
    ) -> None:
        if fill_model != SAME_BAR_CLOSE:
            raise ExecutionError(f"fill model {fill_model!r} is not supported by this adapter")
        self._behavior = behavior or (lambda intent: CompleteFill())
        self._submitted: dict[str, tuple[ExecutionEvent, ...]] = {}

    def submit(self, intent: OrderIntent, bar: ExecutionBar) -> tuple[ExecutionEvent, ...]:
        existing = self._submitted.get(intent.intent_id)
        if existing is not None:
            return existing  # idempotent: same intent_id is the same order, not a new one
        if intent.contract.kind != "primary":
            raise ExecutionError(f"unsupported contract kind {intent.contract.kind!r}")
        outcome = self._behavior(intent)
        ts, price, id_ = bar.timestamp, bar.close, intent.intent_id
        accepted = ExecutionEvent(id_, 1, EventType.ACCEPTED, ts)
        if isinstance(outcome, CompleteFill):
            events = (
                accepted,
                ExecutionEvent(id_, 2, EventType.FILLED, ts, intent.quantity, price),
            )
        elif isinstance(outcome, Reject):
            events = (ExecutionEvent(id_, 1, EventType.REJECTED, ts, reason=outcome.reason),)
        elif isinstance(outcome, PartialFill):
            if not 0 < outcome.quantity < intent.quantity:
                raise ExecutionError("a partial fill must be between zero and the order quantity")
            if outcome.then not in (EventType.EXPIRED, EventType.CANCELLED):
                raise ExecutionError("a partial fill can only end as expired or cancelled")
            events = (
                accepted,
                ExecutionEvent(id_, 2, EventType.PARTIAL_FILL, ts, outcome.quantity, price),
                ExecutionEvent(id_, 3, outcome.then, ts, reason="remainder"),
            )
        else:
            raise ExecutionError(f"unknown simulated outcome {outcome!r}")
        self._submitted[intent.intent_id] = events
        return events
