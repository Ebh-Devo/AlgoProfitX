"""Canonical, typed representation of a Strategy Definition V2.

See docs/STRATEGY_DEFINITION_V2.md. These types only *represent* a definition; they carry
no behaviour beyond serialisation. Which indicators, operations and instrument kinds can
actually run is a capability concern, not a type concern.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Union

SCHEMA_ID = "algoprofitx.strategy-definition"
SCHEMA_VERSION = 2


def _number(value: Decimal) -> int | str:
    """JSON form of a Decimal: an int when integral, otherwise a decimal string."""
    if value == value.to_integral_value():
        return int(value)
    return format(value.normalize(), "f")


# --- Instruments -------------------------------------------------------------------------


@dataclass(frozen=True)
class InstrumentSelector:
    """Describes an instrument. Only ``primary`` (StrategyVersion.instrument_id) exists."""

    kind: Literal["primary"] = "primary"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind}


# --- Operands ----------------------------------------------------------------------------


@dataclass(frozen=True)
class PriceOperand:
    field: Literal["open", "high", "low", "close", "volume"]
    kind: Literal["price"] = "price"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "field": self.field}


@dataclass(frozen=True)
class ConstantOperand:
    value: Decimal
    kind: Literal["constant"] = "constant"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": _number(self.value)}


@dataclass(frozen=True)
class IndicatorRef:
    """A reference to a catalog indicator; the maths is not part of the definition."""

    name: str
    version: int
    params: dict[str, Any]
    source: "Operand | None"
    timeframe: str
    output: str
    kind: Literal["indicator"] = "indicator"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "version": self.version,
            "params": dict(self.params),
            "source": None if self.source is None else self.source.to_dict(),
            "timeframe": self.timeframe,
            "output": self.output,
        }


Operand = Union[PriceOperand, ConstantOperand, IndicatorRef]


# --- Conditions --------------------------------------------------------------------------


@dataclass(frozen=True)
class AllCondition:
    of: tuple["Condition", ...]
    kind: Literal["all"] = "all"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "of": [node.to_dict() for node in self.of]}


@dataclass(frozen=True)
class AnyCondition:
    of: tuple["Condition", ...]
    kind: Literal["any"] = "any"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "of": [node.to_dict() for node in self.of]}


@dataclass(frozen=True)
class NotCondition:
    of: "Condition"
    kind: Literal["not"] = "not"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "of": self.of.to_dict()}


@dataclass(frozen=True)
class CompareCondition:
    op: Literal["gt", "gte", "lt", "lte", "eq"]
    left: Operand
    right: Operand
    kind: Literal["compare"] = "compare"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "op": self.op,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


@dataclass(frozen=True)
class CrossCondition:
    dir: Literal["above", "below"]
    left: Operand
    right: Operand
    kind: Literal["cross"] = "cross"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "dir": self.dir,
            "left": self.left.to_dict(),
            "right": self.right.to_dict(),
        }


@dataclass(frozen=True)
class EdgeCondition:
    dir: Literal["rising"]
    of: "Condition"
    kind: Literal["edge"] = "edge"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "dir": self.dir, "of": self.of.to_dict()}


Condition = Union[
    AllCondition, AnyCondition, NotCondition, CompareCondition, CrossCondition, EdgeCondition
]


# --- Quantity and sizing -----------------------------------------------------------------


@dataclass(frozen=True)
class Quantity:
    """A leg's multiplier on its position's sizing."""

    value: Decimal

    def to_dict(self) -> int | str:
        return _number(self.value)


@dataclass(frozen=True)
class SharesSizing:
    """The only sizing unit authorable in V2.0: an explicit number of shares."""

    value: Decimal
    unit: Literal["shares"] = "shares"

    def to_dict(self) -> dict[str, Any]:
        return {"unit": self.unit, "value": _number(self.value)}


@dataclass(frozen=True)
class PercentOfAllocationSizing:
    """Produced only by the V1 adapter, to reproduce V1's all-in sizing. Not authorable."""

    value: Decimal
    unit: Literal["percent_of_allocation"] = "percent_of_allocation"

    def to_dict(self) -> dict[str, Any]:
        return {"unit": self.unit, "value": _number(self.value)}


Sizing = Union[SharesSizing, PercentOfAllocationSizing]


# --- Legs, risk, positions ---------------------------------------------------------------


@dataclass(frozen=True)
class Leg:
    id: str
    instrument: InstrumentSelector
    side: Literal["buy", "sell"]  # the leg's *opening* direction
    quantity: Quantity
    role: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "instrument": self.instrument.to_dict(),
            "side": self.side,
            "quantity": self.quantity.to_dict(),
        }
        if self.role is not None:
            data["role"] = self.role
        return data


@dataclass(frozen=True)
class LegPriceBasis:
    leg: str
    kind: Literal["leg_price"] = "leg_price"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "leg": self.leg}


@dataclass(frozen=True)
class RiskExit:
    value: Decimal
    basis: LegPriceBasis
    kind: Literal["percent"] = "percent"

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "value": _number(self.value), "basis": self.basis.to_dict()}


@dataclass(frozen=True)
class RiskDefinition:
    stop_loss: RiskExit | None = None
    take_profit: RiskExit | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.stop_loss is not None:
            data["stop_loss"] = self.stop_loss.to_dict()
        if self.take_profit is not None:
            data["take_profit"] = self.take_profit.to_dict()
        return data


@dataclass(frozen=True)
class Position:
    id: str
    role: Literal["core", "hedge"]
    hedges: str | None
    legs: tuple[Leg, ...]
    sizing: Sizing
    template: str | None = None
    risk: RiskDefinition | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.template is not None:
            data["template"] = self.template
        data["role"] = self.role
        data["hedges"] = self.hedges
        data["legs"] = [leg.to_dict() for leg in self.legs]
        data["sizing"] = self.sizing.to_dict()
        if self.risk is not None:
            data["risk"] = self.risk.to_dict()
        return data


# --- Rules and operations ----------------------------------------------------------------


@dataclass(frozen=True)
class Amount:
    unit: Literal["fraction_of_open", "sizing_unit"]
    value: Decimal

    def to_dict(self) -> dict[str, Any]:
        return {"unit": self.unit, "value": _number(self.value)}


@dataclass(frozen=True)
class PositionOperation:
    """A state transition on a position. Carries no order side: that is derived (§10)."""

    op: Literal["open", "close", "increase", "reduce"]
    position: str
    amount: Amount | None = None  # only for increase / reduce

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"op": self.op, "position": self.position}
        if self.amount is not None:
            data["amount"] = self.amount.to_dict()
        return data


@dataclass(frozen=True)
class RuleLimits:
    max_fires_per_position: int

    def to_dict(self) -> dict[str, Any]:
        return {"max_fires_per_position": self.max_fires_per_position}


@dataclass(frozen=True)
class Rule:
    id: str
    when: Condition
    then: tuple[PositionOperation, ...]
    label: str | None = None
    when_position: dict[str, str] | None = None
    priority: int | None = None
    limits: RuleLimits | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"id": self.id}
        if self.label is not None:
            data["label"] = self.label
        data["when"] = self.when.to_dict()
        data["then"] = [operation.to_dict() for operation in self.then]
        if self.when_position is not None:
            data["when_position"] = dict(self.when_position)
        if self.priority is not None:
            data["priority"] = self.priority
        if self.limits is not None:
            data["limits"] = self.limits.to_dict()
        return data


# --- Definition --------------------------------------------------------------------------


@dataclass(frozen=True)
class StrategyDefinition:
    timeframe: str
    evaluation: Literal["bar_close"]
    positions: tuple[Position, ...]
    rules: tuple[Rule, ...]

    def to_dict(self) -> dict[str, Any]:
        """The canonical stored form: fully explicit, loadable by the V2 loader."""
        return {
            "schema": SCHEMA_ID,
            "schema_version": SCHEMA_VERSION,
            "timeframe": self.timeframe,
            "evaluation": self.evaluation,
            "positions": {position.id: position.to_dict() for position in self.positions},
            "rules": [rule.to_dict() for rule in self.rules],
        }


@dataclass(frozen=True)
class CanonicalDefinition:
    """What every future runtime consumer receives, whatever the stored version was.

    ``fill_model`` is the environment default carried by lifted V1 documents
    (``same_bar_close``, spec §13.2); V2 documents leave it ``None`` because the fill model
    is declared in ``backtest_configuration``.
    """

    definition: StrategyDefinition
    source_schema_version: Literal[1, 2]
    fill_model: str | None = None
