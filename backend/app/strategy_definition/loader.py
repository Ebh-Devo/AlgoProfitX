"""The V2 loader: raw stored document -> typed StrategyDefinition, or structured errors.

This validates *structure and cross-references* only (spec §12 layers 1 and the
environment-free parts of 2/3). It knows nothing about which indicators exist or what any
environment can run: indicator semantics belong to the catalog (a later phase) and
capability checks to the capability layer. Errors are collected across independent
objects; an object with missing or unknown fields is reported and its children are not
examined, so one mistake does not cascade into noise. Nothing here is defaulted: every semantically
relevant value must be present in the stored document.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from app.strategy_definition.errors import StrategyDefinitionError, ValidationIssue
from app.strategy_definition.schema import (
    SCHEMA_ID,
    SCHEMA_VERSION,
    AllCondition,
    Amount,
    AnyCondition,
    CompareCondition,
    Condition,
    ConstantOperand,
    CrossCondition,
    EdgeCondition,
    IndicatorRef,
    InstrumentSelector,
    Leg,
    LegPriceBasis,
    NotCondition,
    Operand,
    Position,
    PositionOperation,
    PriceOperand,
    Quantity,
    RiskDefinition,
    RiskExit,
    Rule,
    RuleLimits,
    SharesSizing,
    Sizing,
    StrategyDefinition,
)

ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
TIMEFRAME_PATTERN = re.compile(r"^[1-9][0-9]*[mhdw]$")
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

# Bounds nesting of conditions and indicator sources (spec §22: bound depth).
MAX_DEPTH = 16

_COMPARE_OPS = ("gt", "gte", "lt", "lte", "eq")
_PRICE_FIELDS = ("open", "high", "low", "close", "volume")
_PARAM_TYPES = (int, float, str)


class _Context:
    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []
        self.ids: dict[str, str] = {}

    def error(self, path: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(path, code, message))

    def register_id(self, value: str, path: str) -> None:
        """Position, leg and rule ids share one namespace: unique within the document."""
        if value in self.ids:
            self.error(path, "duplicate_id", f"id {value!r} is already used at {self.ids[value]}")
        else:
            self.ids[value] = path


def _join(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _object(
    ctx: _Context,
    value: Any,
    path: str,
    required: Iterable[str],
    optional: Iterable[str] = (),
) -> dict[str, Any] | None:
    """A strict object: required keys present, no keys outside required+optional."""
    if not isinstance(value, dict):
        ctx.error(path, "invalid_type", "must be an object")
        return None
    required = tuple(required)
    ok = True
    for key in required:
        if key not in value:
            ctx.error(_join(path, key), "missing_field", f"{key} is required")
            ok = False
    allowed = set(required) | set(optional)
    for key in sorted(str(k) for k in value):
        if key not in allowed:
            ctx.error(_join(path, key), "unknown_field", f"unknown field {key!r}")
            ok = False
    return value if ok else None


def _choice(ctx: _Context, value: Any, path: str, allowed: tuple[str, ...]) -> str | None:
    if not isinstance(value, str) or value not in allowed:
        ctx.error(path, "invalid_value", f"must be one of: {', '.join(allowed)}")
        return None
    return value


def _discriminator(
    ctx: _Context,
    node: Any,
    path: str,
    field: str,
    supported: tuple[str, ...],
    reserved: tuple[str, ...],
) -> str | None:
    """Read a ``kind``/``op``/``unit`` tag. Reserved tags are known-but-unsupported."""
    if not isinstance(node, dict):
        ctx.error(path, "invalid_type", "must be an object")
        return None
    if field not in node:
        ctx.error(_join(path, field), "missing_field", f"{field} is required")
        return None
    tag = node[field]
    if isinstance(tag, str) and tag in supported:
        return tag
    if isinstance(tag, str) and tag in reserved:
        ctx.error(
            _join(path, field),
            "unsupported_kind",
            f"{field} {tag!r} is reserved and not supported by schema_version {SCHEMA_VERSION}",
        )
    else:
        ctx.error(_join(path, field), "unknown_kind", f"unknown {field} {tag!r}")
    return None


def _slug(ctx: _Context, value: Any, path: str) -> str | None:
    if not isinstance(value, str) or not ID_PATTERN.match(value):
        ctx.error(path, "invalid_id", "must be a slug: lowercase letters, digits, '_' or '-'")
        return None
    return value


def _decimal(ctx: _Context, value: Any, path: str, code: str = "invalid_number") -> Decimal | None:
    """Parse a JSON number or numeric string to a finite Decimal (never via binary float)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        ctx.error(path, code, "must be a number")
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        ctx.error(path, code, "must be a number")
        return None
    if not parsed.is_finite():
        ctx.error(path, code, "must be a finite number")
        return None
    return parsed


def _positive(ctx: _Context, value: Any, path: str, code: str) -> Decimal | None:
    parsed = _decimal(ctx, value, path, code)
    if parsed is not None and parsed <= 0:
        ctx.error(path, code, "must be greater than zero")
        return None
    return parsed


def _timeframe(ctx: _Context, value: Any, path: str) -> str | None:
    if not isinstance(value, str) or not TIMEFRAME_PATTERN.match(value):
        ctx.error(path, "invalid_timeframe", "must look like 5m, 1h, 1d or 1w")
        return None
    return value


# --- Operands and conditions -------------------------------------------------------------


def _operand(ctx: _Context, node: Any, path: str, depth: int = 0) -> Operand | None:
    if depth > MAX_DEPTH:
        ctx.error(path, "max_depth_exceeded", f"nesting deeper than {MAX_DEPTH}")
        return None
    kind = _discriminator(
        ctx, node, path, "kind", ("price", "constant", "indicator"), ("position", "arith")
    )
    if kind == "price":
        if _object(ctx, node, path, ("kind", "field")) is None:
            return None
        field = _choice(ctx, node["field"], _join(path, "field"), _PRICE_FIELDS)
        return PriceOperand(field) if field else None  # type: ignore[arg-type]
    if kind == "constant":
        if _object(ctx, node, path, ("kind", "value")) is None:
            return None
        value = _decimal(ctx, node["value"], _join(path, "value"))
        return ConstantOperand(value) if value is not None else None
    if kind == "indicator":
        return _indicator(ctx, node, path, depth)
    return None


def _indicator(ctx: _Context, node: dict, path: str, depth: int) -> IndicatorRef | None:
    fields = ("kind", "name", "version", "params", "source", "timeframe", "output")
    if _object(ctx, node, path, fields) is None:
        return None
    ok = True
    name = node["name"]
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        ctx.error(_join(path, "name"), "invalid_indicator", "name must be a lowercase identifier")
        ok = False
    version = node["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        ctx.error(_join(path, "version"), "invalid_indicator", "version must be an integer >= 1")
        ok = False
    params = node["params"]
    if not isinstance(params, dict):
        ctx.error(_join(path, "params"), "invalid_indicator", "params must be an object")
        ok = False
    else:
        for key, value in params.items():
            if not isinstance(key, str) or not NAME_PATTERN.match(key):
                ctx.error(_join(path, "params"), "invalid_indicator", f"invalid param name {key!r}")
                ok = False
            elif isinstance(value, bool) or not isinstance(value, _PARAM_TYPES):
                ctx.error(
                    _join(_join(path, "params"), key),
                    "invalid_indicator",
                    "param values must be numbers or strings",
                )
                ok = False
    source: Operand | None = None
    if node["source"] is not None:
        source = _operand(ctx, node["source"], _join(path, "source"), depth + 1)
        ok = ok and source is not None
    timeframe = _timeframe(ctx, node["timeframe"], _join(path, "timeframe"))
    output = node["output"]
    if not isinstance(output, str) or not NAME_PATTERN.match(output):
        ctx.error(_join(path, "output"), "invalid_indicator", "output must be a lowercase identifier")
        ok = False
    if not ok or timeframe is None:
        return None
    return IndicatorRef(name, version, dict(params), source, timeframe, output)


def _is_series(operand: Operand) -> bool:
    return isinstance(operand, (PriceOperand, IndicatorRef))


def _condition(ctx: _Context, node: Any, path: str, depth: int = 0) -> Condition | None:
    if depth > MAX_DEPTH:
        ctx.error(path, "max_depth_exceeded", f"nesting deeper than {MAX_DEPTH}")
        return None
    kind = _discriminator(
        ctx,
        node,
        path,
        "kind",
        ("all", "any", "not", "compare", "cross", "edge"),
        ("within", "for_bars"),
    )
    if kind in ("all", "any"):
        if _object(ctx, node, path, ("kind", "of")) is None:
            return None
        items = node["of"]
        if not isinstance(items, list) or not items:
            ctx.error(_join(path, "of"), "invalid_condition", "must be a non-empty list")
            return None
        children = [
            _condition(ctx, item, f"{path}.of[{index}]", depth + 1)
            for index, item in enumerate(items)
        ]
        if any(child is None for child in children):
            return None
        return (AllCondition if kind == "all" else AnyCondition)(tuple(children))  # type: ignore[arg-type]
    if kind == "not":
        if _object(ctx, node, path, ("kind", "of")) is None:
            return None
        child = _condition(ctx, node["of"], _join(path, "of"), depth + 1)
        return NotCondition(child) if child is not None else None
    if kind == "edge":
        if _object(ctx, node, path, ("kind", "dir", "of")) is None:
            return None
        direction = _choice(ctx, node["dir"], _join(path, "dir"), ("rising",))
        child = _condition(ctx, node["of"], _join(path, "of"), depth + 1)
        if direction is None or child is None:
            return None
        return EdgeCondition("rising", child)
    if kind == "compare":
        if _object(ctx, node, path, ("kind", "op", "left", "right")) is None:
            return None
        op = _choice(ctx, node["op"], _join(path, "op"), _COMPARE_OPS)
        left = _operand(ctx, node["left"], _join(path, "left"))
        right = _operand(ctx, node["right"], _join(path, "right"))
        if op is None or left is None or right is None:
            return None
        if op == "eq" and (_is_series(left) or _is_series(right)):
            # Exact equality on price/indicator series is a decimal-equality trap (§8.2).
            ctx.error(_join(path, "op"), "invalid_condition", "eq is not allowed on price or indicator series")
            return None
        return CompareCondition(op, left, right)  # type: ignore[arg-type]
    if kind == "cross":
        if _object(ctx, node, path, ("kind", "dir", "left", "right")) is None:
            return None
        direction = _choice(ctx, node["dir"], _join(path, "dir"), ("above", "below"))
        left = _operand(ctx, node["left"], _join(path, "left"))
        right = _operand(ctx, node["right"], _join(path, "right"))
        if direction is None or left is None or right is None:
            return None
        return CrossCondition(direction, left, right)  # type: ignore[arg-type]
    return None


# --- Positions ---------------------------------------------------------------------------


def _sizing(ctx: _Context, node: Any, path: str) -> Sizing | None:
    if isinstance(node, dict) and node.get("unit") == "percent_of_allocation":
        ctx.error(
            _join(path, "unit"),
            "sizing_not_authorable",
            "percent_of_allocation is produced only by the V1 adapter and is not authorable",
        )
        return None
    unit = _discriminator(
        ctx, node, path, "unit", ("shares",), ("contracts", "match_position", "lots")
    )
    if unit != "shares":
        return None
    if _object(ctx, node, path, ("unit", "value")) is None:
        return None
    value = _positive(ctx, node["value"], _join(path, "value"), "invalid_quantity")
    return SharesSizing(value) if value is not None else None


def _leg(ctx: _Context, node: Any, path: str) -> Leg | None:
    if _object(ctx, node, path, ("id", "instrument", "side", "quantity"), ("role",)) is None:
        return None
    leg_id = _slug(ctx, node["id"], _join(path, "id"))
    if leg_id is not None:
        ctx.register_id(leg_id, path)
    instrument = _instrument(ctx, node["instrument"], _join(path, "instrument"))
    side = _choice(ctx, node["side"], _join(path, "side"), ("buy", "sell"))
    value = _positive(ctx, node["quantity"], _join(path, "quantity"), "invalid_quantity")
    role = node.get("role")
    if "role" in node and (not isinstance(role, str) or not role):
        ctx.error(_join(path, "role"), "invalid_value", "must be a non-empty string")
        return None
    if leg_id is None or instrument is None or side is None or value is None:
        return None
    return Leg(leg_id, instrument, side, Quantity(value), role)  # type: ignore[arg-type]


def _instrument(ctx: _Context, node: Any, path: str) -> InstrumentSelector | None:
    kind = _discriminator(ctx, node, path, "kind", ("primary",), ("future", "option"))
    if kind != "primary":
        return None
    if _object(ctx, node, path, ("kind",)) is None:
        return None
    return InstrumentSelector()


def _risk_exit(ctx: _Context, node: Any, path: str, leg_ids: set[str]) -> RiskExit | None:
    kind = _discriminator(ctx, node, path, "kind", ("percent",), ())
    if kind is None or _object(ctx, node, path, ("kind", "value", "basis")) is None:
        return None
    value = _positive(ctx, node["value"], _join(path, "value"), "invalid_risk")
    basis_path = _join(path, "basis")
    basis_kind = _discriminator(
        ctx,
        node["basis"],
        basis_path,
        "kind",
        ("leg_price",),
        ("position_pnl_pct", "position_pnl_amount", "underlying_price", "net_premium"),
    )
    if basis_kind is None or _object(ctx, node["basis"], basis_path, ("kind", "leg")) is None:
        return None
    leg = node["basis"]["leg"]
    if not isinstance(leg, str) or leg not in leg_ids:
        ctx.error(_join(basis_path, "leg"), "unknown_reference", "must name a leg of this position")
        return None
    return RiskExit(value, LegPriceBasis(leg)) if value is not None else None


def _risk(ctx: _Context, node: Any, path: str, leg_ids: set[str]) -> RiskDefinition | None:
    if isinstance(node, dict) and "trailing" in node:
        ctx.error(
            _join(path, "trailing"),
            "unsupported_kind",
            f"trailing is reserved and not supported by schema_version {SCHEMA_VERSION}",
        )
        return None
    if _object(ctx, node, path, (), ("stop_loss", "take_profit")) is None:
        return None
    exits = {
        key: _risk_exit(ctx, node[key], _join(path, key), leg_ids)
        for key in ("stop_loss", "take_profit")
        if key in node
    }
    if any(item is None for item in exits.values()):
        return None
    return RiskDefinition(**exits)


def _position(ctx: _Context, position_id: str, node: Any, path: str) -> Position | None:
    fields = ("role", "hedges", "legs", "sizing")
    if _object(ctx, node, path, fields, ("template", "risk")) is None:
        return None
    ok = _slug(ctx, position_id, path) is not None
    if ok:
        ctx.register_id(position_id, path)
    role = _choice(ctx, node["role"], _join(path, "role"), ("core", "hedge"))
    hedges = node["hedges"]
    if hedges is not None and not isinstance(hedges, str):
        ctx.error(_join(path, "hedges"), "invalid_type", "must be a position id or null")
        ok = False
    elif role == "core" and hedges is not None:
        ctx.error(_join(path, "hedges"), "invalid_position", "a core position cannot hedge another")
        ok = False
    elif role == "hedge" and hedges is None:
        ctx.error(_join(path, "hedges"), "invalid_position", "a hedge position must name the position it hedges")
        ok = False
    elif role == "hedge" and hedges == position_id:
        ctx.error(_join(path, "hedges"), "invalid_position", "a position cannot hedge itself")
        ok = False
    template = node.get("template")
    if "template" in node and (not isinstance(template, str) or not template):
        ctx.error(_join(path, "template"), "invalid_value", "must be a non-empty string")
        ok = False

    legs: list[Leg] = []
    raw_legs = node["legs"]
    if not isinstance(raw_legs, list) or not raw_legs:
        ctx.error(_join(path, "legs"), "invalid_position", "must be a non-empty list of legs")
        ok = False
    else:
        for index, raw_leg in enumerate(raw_legs):
            leg = _leg(ctx, raw_leg, f"{path}.legs[{index}]")
            if leg is None:
                ok = False
            else:
                legs.append(leg)
    sizing = _sizing(ctx, node["sizing"], _join(path, "sizing"))
    risk: RiskDefinition | None = None
    if "risk" in node:
        risk = _risk(ctx, node["risk"], _join(path, "risk"), {leg.id for leg in legs})
        ok = ok and risk is not None
    if not ok or role is None or sizing is None:
        return None
    return Position(position_id, role, hedges, tuple(legs), sizing, template, risk)  # type: ignore[arg-type]


# --- Rules -------------------------------------------------------------------------------


def _operation(ctx: _Context, node: Any, path: str, position_ids: set[str]) -> PositionOperation | None:
    op = _discriminator(
        ctx, node, path, "op", ("open", "close", "increase", "reduce"), ("replace", "adjust")
    )
    if op is None:
        return None
    optional = ("amount",) if op in ("increase", "reduce") else ()
    required = ("op", "position", "amount") if optional else ("op", "position")
    if _object(ctx, node, path, required) is None:
        return None
    position = node["position"]
    ok = True
    if not isinstance(position, str) or position not in position_ids:
        ctx.error(_join(path, "position"), "unknown_reference", "must name a declared position")
        ok = False
    amount = None
    if optional:
        amount = _amount(ctx, node["amount"], _join(path, "amount"), op)
        ok = ok and amount is not None
    return PositionOperation(op, position, amount) if ok else None  # type: ignore[arg-type]


def _amount(ctx: _Context, node: Any, path: str, op: str) -> Amount | None:
    if _object(ctx, node, path, ("unit", "value")) is None:
        return None
    unit = _choice(ctx, node["unit"], _join(path, "unit"), ("fraction_of_open", "sizing_unit"))
    value = _positive(ctx, node["value"], _join(path, "value"), "invalid_amount")
    if unit is None or value is None:
        return None
    if unit == "fraction_of_open" and op == "reduce" and value > 1:
        ctx.error(_join(path, "value"), "invalid_amount", "a reduce fraction must be in (0, 1]")
        return None
    return Amount(unit, value)  # type: ignore[arg-type]


def _rule(ctx: _Context, node: Any, path: str, position_ids: set[str]) -> Rule | None:
    fields = ("id", "when", "then")
    if _object(ctx, node, path, fields, ("label", "when_position", "priority", "limits")) is None:
        return None
    ok = True
    rule_id = _slug(ctx, node["id"], _join(path, "id"))
    if rule_id is None:
        ok = False
    else:
        ctx.register_id(rule_id, path)
    when = _condition(ctx, node["when"], _join(path, "when"))
    ok = ok and when is not None

    operations: list[PositionOperation] = []
    raw_then = node["then"]
    if not isinstance(raw_then, list) or not raw_then:
        ctx.error(_join(path, "then"), "invalid_rule", "must be a non-empty list of operations")
        ok = False
    else:
        for index, raw in enumerate(raw_then):
            operation = _operation(ctx, raw, f"{path}.then[{index}]", position_ids)
            if operation is None:
                ok = False
            else:
                operations.append(operation)

    label = node.get("label")
    if "label" in node and (not isinstance(label, str) or not label):
        ctx.error(_join(path, "label"), "invalid_value", "must be a non-empty string")
        ok = False
    when_position: dict[str, str] | None = None
    if "when_position" in node:
        when_position = _when_position(ctx, node["when_position"], _join(path, "when_position"), position_ids)
        ok = ok and when_position is not None
    priority = node.get("priority")
    if "priority" in node and (isinstance(priority, bool) or not isinstance(priority, int)):
        ctx.error(_join(path, "priority"), "invalid_type", "must be an integer")
        ok = False
    limits: RuleLimits | None = None
    if "limits" in node:
        limits = _limits(ctx, node["limits"], _join(path, "limits"))
        ok = ok and limits is not None
    if not ok:
        return None
    return Rule(rule_id, when, tuple(operations), label, when_position, priority, limits)  # type: ignore[arg-type]


def _when_position(ctx: _Context, node: Any, path: str, position_ids: set[str]) -> dict[str, str] | None:
    if not isinstance(node, dict) or not node:
        ctx.error(path, "invalid_type", "must be a non-empty object of position id -> flat|open")
        return None
    result: dict[str, str] = {}
    for key, state in node.items():
        if key not in position_ids:
            ctx.error(_join(path, str(key)), "unknown_reference", "must name a declared position")
        else:
            checked = _choice(ctx, state, _join(path, key), ("flat", "open"))
            if checked is not None:
                result[key] = checked
    return result if len(result) == len(node) else None


def _limits(ctx: _Context, node: Any, path: str) -> RuleLimits | None:
    if _object(ctx, node, path, ("max_fires_per_position",)) is None:
        return None
    value = node["max_fires_per_position"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        ctx.error(_join(path, "max_fires_per_position"), "invalid_number", "must be an integer >= 1")
        return None
    return RuleLimits(value)


# --- Entry point -------------------------------------------------------------------------


def load_v2_definition(document: Any) -> StrategyDefinition:
    """Load a stored V2 document, or raise ``StrategyDefinitionError`` listing every issue."""
    ctx = _Context()
    definition = _load(ctx, document)
    if ctx.issues or definition is None:
        raise StrategyDefinitionError(ctx.issues)
    return definition


def _load(ctx: _Context, document: Any) -> StrategyDefinition | None:
    if not isinstance(document, dict):
        ctx.error("", "invalid_document", "a strategy definition must be an object")
        return None

    # The envelope is checked first: a document that is not explicitly V2 is not read further.
    if "schema" not in document:
        ctx.error("schema", "missing_field", "schema is required")
    elif document["schema"] != SCHEMA_ID:
        ctx.error("schema", "invalid_schema", f"schema must be {SCHEMA_ID!r}")
    if "schema_version" not in document:
        ctx.error("schema_version", "missing_field", "schema_version is required")
    else:
        version = document["schema_version"]
        if isinstance(version, bool) or version != SCHEMA_VERSION:
            ctx.error(
                "schema_version",
                "unsupported_schema_version",
                f"schema_version must be {SCHEMA_VERSION}",
            )
    if ctx.issues:
        return None

    fields = ("schema", "schema_version", "timeframe", "evaluation", "positions", "rules")
    if _object(ctx, document, "", fields) is None:
        return None
    ok = True
    timeframe = _timeframe(ctx, document["timeframe"], "timeframe")
    evaluation = _choice(ctx, document["evaluation"], "evaluation", ("bar_close",))
    ok = timeframe is not None and evaluation is not None

    raw_positions = document["positions"]
    positions: list[Position] = []
    position_ids: set[str] = set()
    if not isinstance(raw_positions, dict) or not raw_positions:
        ctx.error("positions", "invalid_type", "must be a non-empty object of positions")
        ok = False
    else:
        position_ids = {str(key) for key in raw_positions}
        for key, raw in raw_positions.items():
            position = _position(ctx, str(key), raw, f"positions.{key}")
            if position is None:
                ok = False
            else:
                positions.append(position)
        for position in positions:
            if position.hedges is not None and position.hedges not in position_ids:
                ctx.error(
                    f"positions.{position.id}.hedges",
                    "unknown_reference",
                    "must name a declared position",
                )
                ok = False

    raw_rules = document["rules"]
    rules: list[Rule] = []
    if not isinstance(raw_rules, list) or not raw_rules:
        ctx.error("rules", "invalid_type", "must be a non-empty list of rules")
        ok = False
    else:
        for index, raw in enumerate(raw_rules):
            rule = _rule(ctx, raw, f"rules[{index}]", position_ids)
            if rule is None:
                ok = False
            else:
                rules.append(rule)

    if not ok or ctx.issues:
        return None
    return StrategyDefinition(timeframe, evaluation, tuple(positions), tuple(rules))  # type: ignore[arg-type]
