"""Layer 3 (spec §12): is the position lifecycle coherent?

Static analysis of positions × rules × operations over a typed ``StrategyDefinition``. This
is deliberately *not* a state machine: it only rejects what can be proven impossible from the
definition alone (e.g. closing a position no rule can open). Anything that merely depends on
runtime state is accepted. Issues come back in definition order (deterministic).
"""

from decimal import Decimal
from typing import Any

from app.strategy_definition.errors import ValidationIssue
from app.strategy_definition.schema import (
    InstrumentSelector,
    LegPriceBasis,
    PercentOfAllocationSizing,
    Position,
    PositionOperation,
    RiskExit,
    Rule,
    SharesSizing,
    StrategyDefinition,
)

_OPERATIONS = ("open", "close", "increase", "reduce")
_AMOUNT_OPERATIONS = ("increase", "reduce")


def validate_position_semantics(definition: StrategyDefinition) -> tuple[ValidationIssue, ...]:
    """Every Layer 3 issue in ``definition``; empty when its lifecycle is coherent."""
    return tuple(_Positions(definition).run())


class _Positions:
    def __init__(self, definition: StrategyDefinition) -> None:
        self.definition = definition
        self.issues: list[ValidationIssue] = []
        self.ids: dict[str, str] = {}
        self.by_id = {position.id: position for position in definition.positions}
        # Positions some rule can ``open``: the only ones other operations can ever act on.
        self.openable = {
            operation.position
            for rule in definition.rules
            for operation in rule.then
            if operation.op == "open"
        }

    def error(self, path: str, code: str, message: str, severity: str = "error") -> None:
        self.issues.append(ValidationIssue(path, code, message, severity))

    def warning(self, path: str, code: str, message: str) -> None:
        self.error(path, code, message, "warning")

    def register_id(self, value: str, path: str) -> None:
        """Position, leg and rule ids share one namespace (same as the loader)."""
        if value in self.ids:
            self.error(path, "duplicate_id", f"id {value!r} is already used at {self.ids[value]}")
        else:
            self.ids[value] = path

    def run(self) -> list[ValidationIssue]:
        for position in self.definition.positions:
            self.position(position)
        for index, rule in enumerate(self.definition.rules):
            self.rule(rule, f"rules[{index}]")
        self.hedge_lifecycles()
        return self.issues

    # --- Positions ----------------------------------------------------------------------

    def position(self, position: Position) -> None:
        path = f"positions.{position.id}"
        self.register_id(position.id, path)
        self.hedging(position, path)
        self.legs(position, path)
        self.sizing(position, path)
        if position.risk is not None:
            for name in ("stop_loss", "take_profit"):
                exit_ = getattr(position.risk, name)
                if exit_ is not None:
                    self.risk_exit(position, exit_, f"{path}.risk.{name}")

    def hedging(self, position: Position, path: str) -> None:
        """A hedge names exactly one core position. Because only a core can be a target, a
        hedge-of-hedge chain, and therefore any hedge cycle, is rejected here."""
        hedges_path = f"{path}.hedges"
        if position.role == "core":
            if position.hedges is not None:
                self.error(hedges_path, "invalid_position", "a core position cannot hedge another")
        elif position.role == "hedge":
            if position.hedges is None:
                self.error(hedges_path, "invalid_position", "a hedge position must name the position it hedges")
            elif position.hedges == position.id:
                self.error(hedges_path, "invalid_position", "a position cannot hedge itself")
            elif position.hedges not in self.by_id:
                self.error(hedges_path, "unknown_reference", "must name a declared position")
            elif self.by_id[position.hedges].role != "core":
                self.error(
                    hedges_path,
                    "invalid_hedge_target",
                    "a hedge must protect a core position, not another hedge",
                )
        else:
            self.error(f"{path}.role", "invalid_value", "must be one of: core, hedge")

    def legs(self, position: Position, path: str) -> None:
        if not position.legs:
            self.error(f"{path}.legs", "invalid_position", "must be a non-empty list of legs")
        for index, leg in enumerate(position.legs):
            leg_path = f"{path}.legs[{index}]"
            self.register_id(leg.id, leg_path)
            if not isinstance(leg.instrument, InstrumentSelector) or leg.instrument.kind != "primary":
                self.error(f"{leg_path}.instrument", "unsupported_kind", "only the primary instrument is supported")
            if leg.side not in ("buy", "sell"):
                self.error(f"{leg_path}.side", "invalid_value", "must be one of: buy, sell")
            if not _positive(leg.quantity.value):
                self.error(f"{leg_path}.quantity", "invalid_quantity", "must be greater than zero")

    def sizing(self, position: Position, path: str) -> None:
        sizing = position.sizing
        if isinstance(sizing, PercentOfAllocationSizing):
            self.error(
                f"{path}.sizing.unit",
                "sizing_not_authorable",
                "percent_of_allocation is produced only by the V1 adapter and is not authorable",
            )
        elif not isinstance(sizing, SharesSizing):
            self.error(f"{path}.sizing.unit", "unsupported_kind", "only shares sizing is supported")
        elif not _positive(sizing.value):
            self.error(f"{path}.sizing.value", "invalid_quantity", "must be greater than zero")

    def risk_exit(self, position: Position, exit_: RiskExit, path: str) -> None:
        if exit_.kind != "percent":
            self.error(f"{path}.kind", "unsupported_kind", "only percent risk exits are supported")
        if not _positive(exit_.value):
            self.error(f"{path}.value", "invalid_risk", "must be greater than zero")
        basis = exit_.basis
        if not isinstance(basis, LegPriceBasis):
            self.error(f"{path}.basis", "unsupported_kind", "only leg_price risk bases are supported")
        elif basis.leg not in {leg.id for leg in position.legs}:
            self.error(f"{path}.basis.leg", "unknown_reference", "must name a leg of this position")

    # --- Rules and operations -----------------------------------------------------------

    def rule(self, rule: Rule, path: str) -> None:
        self.register_id(rule.id, path)
        if not rule.then:
            self.error(f"{path}.then", "invalid_rule", "must be a non-empty list of operations")
        for index, operation in enumerate(rule.then):
            self.operation(operation, f"{path}.then[{index}]")
        self.conflicts(rule, path)
        if rule.when_position is not None:
            self.when_position(rule.when_position, f"{path}.when_position")
        if rule.limits is not None and (
            isinstance(rule.limits.max_fires_per_position, bool)
            or rule.limits.max_fires_per_position < 1
        ):
            self.error(f"{path}.limits.max_fires_per_position", "invalid_number", "must be an integer >= 1")

    def operation(self, operation: PositionOperation, path: str) -> None:
        if operation.op not in _OPERATIONS:
            self.error(f"{path}.op", "unknown_kind", f"unknown op {operation.op!r}")
            return
        if operation.position not in self.by_id:
            self.error(f"{path}.position", "unknown_reference", "must name a declared position")
        elif operation.op != "open" and operation.position not in self.openable:
            # Static only: no rule opens it, so it can never be open. Whether it is open at
            # a given bar is runtime state and is not judged here.
            self.error(
                f"{path}.position",
                "position_never_opened",
                f"{operation.op} acts on {operation.position!r}, which no rule can open",
            )
        self.amount(operation, path)

    def amount(self, operation: PositionOperation, path: str) -> None:
        amount = operation.amount
        if operation.op not in _AMOUNT_OPERATIONS:
            if amount is not None:
                self.error(f"{path}.amount", "invalid_operation", f"{operation.op} takes no amount")
            return
        if amount is None:
            self.error(f"{path}.amount", "invalid_operation", f"{operation.op} requires an amount")
        elif amount.unit not in ("fraction_of_open", "sizing_unit"):
            self.error(f"{path}.amount.unit", "invalid_value", "must be one of: fraction_of_open, sizing_unit")
        elif not _positive(amount.value):
            self.error(f"{path}.amount.value", "invalid_amount", "must be greater than zero")
        elif amount.unit == "fraction_of_open" and operation.op == "reduce" and amount.value > 1:
            self.error(f"{path}.amount.value", "invalid_amount", "a reduce fraction must be in (0, 1]")

    def conflicts(self, rule: Rule, path: str) -> None:
        """One rule that both opens and closes a position cannot do both on one bar (§11.3)."""
        by_position: dict[str, set[str]] = {}
        for operation in rule.then:
            by_position.setdefault(operation.position, set()).add(operation.op)
        for position_id, ops in by_position.items():
            if {"open", "close"} <= ops:
                self.warning(
                    f"{path}.then",
                    "conflicting_operations",
                    f"rule both opens and closes {position_id!r}; the close wins and the open is dropped",
                )

    def when_position(self, guard: dict[str, str], path: str) -> None:
        for position_id, state in guard.items():
            if position_id not in self.by_id:
                self.error(f"{path}.{position_id}", "unknown_reference", "must name a declared position")
            elif state not in ("flat", "open"):
                self.error(f"{path}.{position_id}", "invalid_value", "must be one of: flat, open")
            elif state == "open" and position_id not in self.openable:
                self.error(
                    f"{path}.{position_id}",
                    "rule_never_fires",
                    f"requires {position_id!r} to be open, but no rule can open it",
                )

    # --- Hedges -------------------------------------------------------------------------

    def hedge_lifecycles(self) -> None:
        """A hedge can outlive the position it protects (warning, §12)."""
        closed = {
            operation.position
            for rule in self.definition.rules
            for operation in rule.then
            if operation.op == "close"
        }
        for position in self.definition.positions:
            if position.role != "hedge" or position.hedges not in self.by_id:
                continue
            parent = self.by_id[position.hedges]
            path = f"positions.{position.id}"
            if position.hedges not in self.openable and position.id in self.openable:
                self.warning(
                    f"{path}.hedges",
                    "hedge_parent_never_opened",
                    f"{position.id!r} can open but the position it hedges ({parent.id!r}) never can",
                )
            elif _can_exit(parent, closed) and not _can_exit(position, closed):
                self.warning(
                    f"{path}.hedges",
                    "hedge_may_outlive_parent",
                    f"{parent.id!r} can be closed but nothing closes the hedge {position.id!r}",
                )


def _can_exit(position: Position, closed: set[str]) -> bool:
    risk = position.risk
    return position.id in closed or (
        risk is not None and (risk.stop_loss is not None or risk.take_profit is not None)
    )


def _positive(value: Any) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0
