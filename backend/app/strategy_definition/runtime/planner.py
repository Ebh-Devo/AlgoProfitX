"""The order planner: position operations -> broker-independent order intents (spec §14.2).

Responsibilities: resolve each leg's instrument, derive the order side from the operation and
the leg's opening direction, size the order from the explicit V2 sizing, and attach the
deterministic ids. It does not evaluate conditions, execute orders or touch the ledger.
"""

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.strategy_definition.runtime.errors import (
    RuntimeDataError,
    RuntimeSetupError,
    UnsupportedOperationError,
)
from app.strategy_definition.runtime.intents import (
    DEFAULT_GROUP_POLICY,
    OrderConstraints,
    OrderIntent,
    ResolvedContract,
    make_group_id,
    make_intent_id,
)
from app.strategy_definition.runtime.operations import CandidateOperation
from app.strategy_definition.runtime.state import PositionSnapshot
from app.strategy_definition.schema import (
    InstrumentSelector,
    PercentOfAllocationSizing,
    Position,
    SharesSizing,
    StrategyDefinition,
)

_OPPOSITE = {"buy": "sell", "sell": "buy"}
_PLANNABLE_OPERATIONS = frozenset({"open", "close"})


def derive_side(op: str, leg_side: str) -> str:
    """Order side from the operation and the leg's *opening* direction (spec §10.3).

    ``open``/``increase`` trade with the leg; ``close``/``reduce`` trade against it. No exit
    side is ever stored or read: it is always derived here.
    """
    if leg_side not in _OPPOSITE:
        raise RuntimeSetupError(f"unknown leg side {leg_side!r}")
    if op in ("open", "increase"):
        return leg_side
    if op in ("close", "reduce"):
        return _OPPOSITE[leg_side]
    raise UnsupportedOperationError(f"cannot derive an order side for operation {op!r}")


class InstrumentResolver(Protocol):
    def resolve(self, selector: InstrumentSelector, as_of: datetime) -> ResolvedContract: ...


class PrimaryInstrumentResolver:
    """V2.0's only resolver: ``{"kind": "primary"}`` is StrategyVersion.instrument_id."""

    def __init__(self, instrument_ref: str = "primary") -> None:
        self._instrument_ref = instrument_ref

    def resolve(self, selector: InstrumentSelector, as_of: datetime) -> ResolvedContract:
        if selector.kind != "primary":
            raise RuntimeSetupError(f"instrument selector {selector.kind!r} is not supported")
        return ResolvedContract("primary", self._instrument_ref)


class OrderPlanner:
    def __init__(
        self,
        definition: StrategyDefinition,
        *,
        strategy_version_id: str,
        allocation: Decimal,
        resolver: InstrumentResolver,
        group_policy: str = DEFAULT_GROUP_POLICY,
    ) -> None:
        self._positions = {position.id: position for position in definition.positions}
        self._strategy_version_id = strategy_version_id
        self._allocation = allocation
        self._resolver = resolver
        self._group_policy = group_policy

    def plan(
        self,
        candidate: CandidateOperation,
        snapshot: PositionSnapshot,
        *,
        bar_timestamp: datetime,
        reference_price: Decimal,
    ) -> tuple[OrderIntent, ...]:
        """One intent per leg, from the *pre-bar* position snapshot."""
        operation = candidate.operation
        if operation.op not in _PLANNABLE_OPERATIONS:
            raise UnsupportedOperationError(
                f"operation {operation.op!r} is reserved, not implemented"
            )
        if reference_price <= 0:
            raise RuntimeDataError("the reference price must be positive")
        position = self._positions[operation.position]
        group_id = make_group_id(
            self._strategy_version_id, candidate.source, bar_timestamp, candidate.op_index
        )
        intents: list[OrderIntent] = []
        for leg in position.legs:
            if operation.op == "open":
                quantity = self._open_quantity(position, leg.quantity.value, reference_price)
            else:
                quantity = abs(snapshot.leg(leg.id).quantity)
            if quantity <= 0:
                continue  # a leg with nothing held has nothing to close
            intents.append(
                OrderIntent(
                    intent_id=make_intent_id(
                        self._strategy_version_id,
                        candidate.source,
                        bar_timestamp,
                        candidate.op_index,
                        leg.id,
                    ),
                    group_id=group_id,
                    position=position.id,
                    leg=leg.id,
                    op=operation.op,
                    contract=self._resolver.resolve(leg.instrument, bar_timestamp),
                    side=derive_side(operation.op, leg.side),
                    quantity=quantity,
                    constraints=OrderConstraints(reference_price=reference_price),
                    group_policy=self._group_policy,
                    signal_ts=bar_timestamp,
                    source=candidate.source,
                )
            )
        return tuple(intents)

    def _open_quantity(
        self, position: Position, leg_multiplier: Decimal, reference_price: Decimal
    ) -> Decimal:
        sizing = position.sizing
        if isinstance(sizing, SharesSizing):
            return sizing.value * leg_multiplier
        if isinstance(sizing, PercentOfAllocationSizing):
            # Produced only by the V1 adapter (spec §7.3): an explicit sizing unit in the
            # definition, resolved against the environment's allocation. Not authorable.
            return self._allocation * sizing.value / Decimal(100) / reference_price * leg_multiplier
        raise RuntimeSetupError(f"unsupported sizing unit {getattr(sizing, 'unit', sizing)!r}")
