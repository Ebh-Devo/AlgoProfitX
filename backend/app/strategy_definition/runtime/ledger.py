"""The ledger: the only owner of "what is actually held" (spec §14.4).

Holdings, cash, P&L, trade lifecycle and position status change *only* when an execution
event is applied. ``track_order`` merely registers that an order is working (so ``opening`` /
``closing`` are derivable); it never changes a quantity. Everything is ``Decimal``, and the
same journal replayed into a fresh ledger yields an identical state.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence

from app.strategy_definition.runtime.errors import LedgerInconsistencyError, RuntimeDataError
from app.strategy_definition.runtime.execution import EventType, ExecutionEvent
from app.strategy_definition.runtime.intents import OrderIntent
from app.strategy_definition.runtime.operations import OperationSource
from app.strategy_definition.runtime.state import (
    LegSnapshot,
    PositionSnapshot,
    PositionStatus,
    RuntimeSnapshot,
)
from app.strategy_definition.runtime.state_machine import derive_status
from app.strategy_definition.schema import StrategyDefinition

LegKey = tuple[str, str]  # (position_id, leg_id)


@dataclass(frozen=True)
class LedgerLegSpec:
    leg_id: str
    side: str  # the leg's opening direction: buy -> long, sell -> short
    ratio: Decimal  # the leg's quantity multiplier (fixed leg ratios, spec §10.3)


@dataclass(frozen=True)
class LedgerPositionSpec:
    position_id: str
    legs: tuple[LedgerLegSpec, ...]


def ledger_specs(definition: StrategyDefinition) -> tuple[LedgerPositionSpec, ...]:
    return tuple(
        LedgerPositionSpec(
            position.id,
            tuple(LedgerLegSpec(leg.id, leg.side, leg.quantity.value) for leg in position.legs),
        )
        for position in definition.positions
    )


@dataclass(frozen=True)
class OrderRegistration:
    """The working-order facts the ledger needs; deliberately not the whole intent."""

    intent_id: str
    position: str
    leg: str
    op: str
    side: str
    quantity: Decimal
    signal_ts: datetime
    source: OperationSource

    @classmethod
    def from_intent(cls, intent: OrderIntent) -> "OrderRegistration":
        return cls(
            intent.intent_id,
            intent.position,
            intent.leg,
            intent.op,
            intent.side,
            intent.quantity,
            intent.signal_ts,
            intent.source,
        )


JournalEntry = OrderRegistration | ExecutionEvent


class OrderState(str, Enum):
    CREATED = "created"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


_WORKING = frozenset({OrderState.CREATED, OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED})
# event type -> (states it may arrive in, state it leads to; None = decided by the fill total)
_TRANSITIONS: dict[EventType, tuple[frozenset[OrderState], OrderState | None]] = {
    EventType.ACCEPTED: (frozenset({OrderState.CREATED}), OrderState.ACKNOWLEDGED),
    EventType.PARTIAL_FILL: (
        frozenset({OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED}),
        OrderState.PARTIALLY_FILLED,
    ),
    EventType.FILLED: (frozenset({OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED}), None),
    EventType.REJECTED: (
        frozenset({OrderState.CREATED, OrderState.ACKNOWLEDGED}),
        OrderState.REJECTED,
    ),
    EventType.CANCELLED: (
        frozenset({OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED}),
        OrderState.CANCELLED,
    ),
    EventType.EXPIRED: (
        frozenset({OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED}),
        OrderState.EXPIRED,
    ),
}


class _Order:
    def __init__(self, registration: OrderRegistration) -> None:
        self.registration = registration
        self.state = OrderState.CREATED
        self.filled = Decimal(0)
        self.last_seq = 0


class _Average:
    """Quantity-weighted average price. A single fill's average is that fill's price exactly."""

    def __init__(self) -> None:
        self.quantity = Decimal(0)
        self.price: Decimal | None = None

    def add(self, quantity: Decimal, price: Decimal) -> None:
        if self.price is None:
            self.price = price
        else:
            self.price = (self.quantity * self.price + quantity * price) / (self.quantity + quantity)
        self.quantity += quantity


class _LegState:
    def __init__(self, spec: LedgerLegSpec) -> None:
        self.spec = spec
        self.held = Decimal(0)  # signed
        self.average: Decimal | None = None


class _TradeLeg:
    def __init__(self, spec: LedgerLegSpec) -> None:
        self.spec = spec
        self.entry = _Average()
        self.exit = _Average()
        self.realised = Decimal(0)
        self.fees = Decimal(0)


@dataclass(frozen=True)
class TradeLeg:
    leg_id: str
    side: str  # "long" | "short"
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realised_pnl: Decimal
    fees: Decimal


@dataclass(frozen=True)
class Trade:
    """One position lifecycle, flat -> flat. Signal and fill timestamps are kept separately."""

    position_id: str
    legs: tuple[TradeLeg, ...]
    signal_ts: datetime
    fill_ts: datetime
    exit_signal_ts: datetime | None  # None when the exit was engine-issued, not a signal
    exit_fill_ts: datetime
    exit_reason: str
    pnl: Decimal  # net of fees


class _OpenTrade:
    def __init__(self, position: LedgerPositionSpec, signal_ts: datetime, fill_ts: datetime):
        self.position_id = position.position_id
        self.signal_ts = signal_ts
        self.fill_ts = fill_ts
        self.legs = {leg.leg_id: _TradeLeg(leg) for leg in position.legs}


class Ledger:
    def __init__(self, positions: Sequence[LedgerPositionSpec], initial_capital: Decimal):
        if initial_capital <= 0:
            raise ValueError("initial_capital must be positive")
        self._specs = {spec.position_id: spec for spec in positions}
        self._legs: dict[LegKey, _LegState] = {
            (spec.position_id, leg.leg_id): _LegState(leg)
            for spec in positions
            for leg in spec.legs
        }
        self.initial_capital = initial_capital
        self._cash = initial_capital
        self._realised = Decimal(0)
        self._fees = Decimal(0)
        self._orders: dict[str, _Order] = {}
        self._seen: dict[tuple[str, int], ExecutionEvent] = {}
        self._open_trades: dict[str, _OpenTrade] = {}
        self._trades: list[Trade] = []
        self._journal: list[JournalEntry] = []

    # --- Inputs ----------------------------------------------------------------------------

    def track_order(self, intent: OrderIntent) -> None:
        """Register a working order. Changes no quantity: only fills do."""
        self._register(OrderRegistration.from_intent(intent))

    def apply_event(self, event: ExecutionEvent) -> None:
        """Apply one execution event; an exact duplicate is ignored, a conflicting one raises."""
        key = (event.intent_id, event.event_seq)
        previous = self._seen.get(key)
        if previous is not None:
            if previous != event:
                raise LedgerInconsistencyError(f"conflicting duplicate event {key}")
            return
        order = self._orders.get(event.intent_id)
        if order is None:
            raise LedgerInconsistencyError(f"event for unknown intent {event.intent_id}")
        if event.event_seq <= order.last_seq:
            raise LedgerInconsistencyError(
                f"event_seq {event.event_seq} is not after {order.last_seq} for {event.intent_id}"
            )
        allowed, target = _TRANSITIONS[event.type]
        if order.state not in allowed:
            raise LedgerInconsistencyError(
                f"{event.type.value} is not legal for an order that is {order.state.value}"
            )
        if event.type in (EventType.PARTIAL_FILL, EventType.FILLED):
            target = self._fill(order, event)
        order.state = target
        order.last_seq = event.event_seq
        self._seen[key] = event
        self._journal.append(event)

    @classmethod
    def replay(
        cls,
        positions: Sequence[LedgerPositionSpec],
        initial_capital: Decimal,
        journal: Sequence[JournalEntry],
    ) -> "Ledger":
        """Rebuild a ledger from a journal; the result equals the ledger that wrote it."""
        ledger = cls(positions, initial_capital)
        for entry in journal:
            if isinstance(entry, OrderRegistration):
                ledger._register(entry)
            else:
                ledger.apply_event(entry)
        return ledger

    # --- Reads -----------------------------------------------------------------------------

    @property
    def journal(self) -> tuple[JournalEntry, ...]:
        return tuple(self._journal)

    @property
    def trades(self) -> tuple[Trade, ...]:
        return tuple(self._trades)

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def realised_pnl(self) -> Decimal:
        return self._realised

    @property
    def fees(self) -> Decimal:
        return self._fees

    def held(self, position_id: str, leg_id: str) -> Decimal:
        return self._legs[(position_id, leg_id)].held

    def average_entry_price(self, position_id: str, leg_id: str) -> Decimal | None:
        return self._legs[(position_id, leg_id)].average

    def status(self, position_id: str) -> PositionStatus:
        spec = self._specs[position_id]
        held = {leg.leg_id: self._legs[(position_id, leg.leg_id)].held for leg in spec.legs}
        ratios = {leg.leg_id: leg.ratio for leg in spec.legs}
        working = {
            order.registration.op
            for order in self._orders.values()
            if order.registration.position == position_id and order.state in _WORKING
        }
        return derive_status(held, ratios, working)

    def snapshot(self) -> RuntimeSnapshot:
        """An immutable view of the ledger as it is now."""
        return RuntimeSnapshot(
            tuple(
                PositionSnapshot(
                    spec.position_id,
                    self.status(spec.position_id),
                    tuple(
                        LegSnapshot(
                            leg.leg_id,
                            self._legs[(spec.position_id, leg.leg_id)].held,
                            self._legs[(spec.position_id, leg.leg_id)].average,
                        )
                        for leg in spec.legs
                    ),
                )
                for spec in self._specs.values()
            )
        )

    def unrealised_pnl(self, marks: Mapping[LegKey, Decimal]) -> Decimal:
        total = Decimal(0)
        for key, leg in self._legs.items():
            if leg.held == 0:
                continue
            mark = marks.get(key)
            if mark is None:
                raise RuntimeDataError(f"no mark price for held leg {key}")
            total += leg.held * (mark - leg.average)
        return total

    def equity(self, marks: Mapping[LegKey, Decimal]) -> Decimal:
        """Initial capital + realised + unrealised - fees (equals cash + market value)."""
        return self.initial_capital + self._realised + self.unrealised_pnl(marks) - self._fees

    def market_value(self, marks: Mapping[LegKey, Decimal]) -> Decimal:
        total = Decimal(0)
        for key, leg in self._legs.items():
            if leg.held != 0:
                mark = marks.get(key)
                if mark is None:
                    raise RuntimeDataError(f"no mark price for held leg {key}")
                total += leg.held * mark
        return total

    # --- Internals -------------------------------------------------------------------------

    def _register(self, registration: OrderRegistration) -> None:
        if registration.intent_id in self._orders:
            raise LedgerInconsistencyError(f"intent {registration.intent_id} is already tracked")
        if (registration.position, registration.leg) not in self._legs:
            raise LedgerInconsistencyError(
                f"order for unknown leg {registration.position}/{registration.leg}"
            )
        if registration.side not in ("buy", "sell") or registration.quantity <= 0:
            raise LedgerInconsistencyError(f"invalid order {registration.intent_id}")
        self._orders[registration.intent_id] = _Order(registration)
        self._journal.append(registration)

    def _fill(self, order: _Order, event: ExecutionEvent) -> OrderState:
        quantity, price = event.filled_qty, event.price
        if quantity is None or price is None or quantity <= 0 or price <= 0 or event.fees < 0:
            raise LedgerInconsistencyError(f"{event.type.value} needs positive qty and price")
        registration = order.registration
        total = order.filled + quantity
        if total > registration.quantity:
            raise LedgerInconsistencyError(f"over-fill of {registration.intent_id}")
        if event.type is EventType.FILLED and total != registration.quantity:
            raise LedgerInconsistencyError(f"'filled' leaves {registration.intent_id} incomplete")
        if event.type is EventType.PARTIAL_FILL and total == registration.quantity:
            raise LedgerInconsistencyError(f"'partial_fill' completes {registration.intent_id}")
        self._apply_fill(registration, quantity, price, event.fees, event.ts)
        order.filled = total
        return OrderState.FILLED if total == registration.quantity else OrderState.PARTIALLY_FILLED

    def _apply_fill(
        self,
        order: OrderRegistration,
        quantity: Decimal,
        price: Decimal,
        fees: Decimal,
        ts: datetime,
    ) -> None:
        position = self._specs[order.position]
        leg = self._legs[(order.position, order.leg)]
        if all(self._legs[(order.position, spec.leg_id)].held == 0 for spec in position.legs):
            self._open_trades[order.position] = _OpenTrade(position, order.signal_ts, ts)
        trade_leg = self._open_trades[order.position].legs[order.leg]

        sign = Decimal(1) if order.side == "buy" else Decimal(-1)
        delta = sign * quantity
        if leg.held == 0 or (leg.held > 0) == (delta > 0):
            leg.average = price if leg.held == 0 else (
                (abs(leg.held) * leg.average + quantity * price) / (abs(leg.held) + quantity)
            )
            trade_leg.entry.add(quantity, price)
        else:
            if quantity > abs(leg.held):
                raise LedgerInconsistencyError(
                    f"a {order.side} of {quantity} would flip {order.position}/{order.leg}"
                )
            held_sign = Decimal(1) if leg.held > 0 else Decimal(-1)
            gain = held_sign * quantity * (price - leg.average)
            self._realised += gain
            trade_leg.realised += gain
            trade_leg.exit.add(quantity, price)
        leg.held += delta
        if leg.held == 0:
            leg.average = None
        self._cash -= delta * price + fees
        self._fees += fees
        trade_leg.fees += fees

        if all(self._legs[(order.position, spec.leg_id)].held == 0 for spec in position.legs):
            self._close_trade(position, order, ts)

    def _close_trade(
        self, position: LedgerPositionSpec, order: OrderRegistration, ts: datetime
    ) -> None:
        open_trade = self._open_trades.pop(position.position_id)
        legs = tuple(
            TradeLeg(
                leg_id=trade_leg.spec.leg_id,
                side="long" if trade_leg.spec.side == "buy" else "short",
                quantity=trade_leg.entry.quantity,
                entry_price=trade_leg.entry.price,
                exit_price=trade_leg.exit.price,
                realised_pnl=trade_leg.realised,
                fees=trade_leg.fees,
            )
            for trade_leg in open_trade.legs.values()
            if trade_leg.entry.price is not None
        )
        self._trades.append(
            Trade(
                position_id=position.position_id,
                legs=legs,
                signal_ts=open_trade.signal_ts,
                fill_ts=open_trade.fill_ts,
                exit_signal_ts=None if order.source.kind == "engine" else order.signal_ts,
                exit_fill_ts=ts,
                exit_reason=order.source.reason,
                pnl=sum((leg.realised_pnl for leg in legs), Decimal(0))
                - sum((leg.fees for leg in legs), Decimal(0)),
            )
        )
