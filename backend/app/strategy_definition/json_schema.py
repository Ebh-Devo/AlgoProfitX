"""Deterministic JSON Schema (draft 2020-12) for the V2 *authoring* vocabulary.

The schema describes what an author may write in a stored V2 document. It is derived from the
same constants the loader uses (patterns, closed vocabularies) and deliberately excludes
V1-compatibility-only concepts: ``percent_of_allocation`` sizing, which only the V1 adapter
produces, is not authorable and does not appear here. Reserved-but-unsupported grammar
(options, ``within``, trailing stops, ...) is likewise absent, so closed objects reject it.

The loader remains the source of behavioural truth. The schema is a structural projection of
it; tests run both over a shared corpus so the two cannot silently drift.
"""

import json
from typing import Any

from app.strategy_definition.loader import (
    _COMPARE_OPS,
    _PRICE_FIELDS,
    DECIMAL_PATTERN,
    ID_PATTERN,
    MAX_DEPTH,
    NAME_PATTERN,
    POSITIVE_DECIMAL_PATTERN,
    TIMEFRAME_PATTERN,
)
from app.strategy_definition.schema import SCHEMA_ID, SCHEMA_VERSION

JSON_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

NOT_REPRESENTABLE = (
    "Enforced by the loader only: cross-references (position, leg and hedges ids must exist; "
    "a hedge cannot hedge itself), id uniqueness across positions/legs/rules, a reduce "
    f"fraction_of_open value of at most 1, positivity of decimal strings, and the nesting "
    f"depth limit of {MAX_DEPTH} for conditions and indicator sources (the schema is "
    "recursive and does not unroll it)."
)


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/$defs/{name}"}


def _const(value: Any) -> dict[str, Any]:
    return {"const": value}


def _closed(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    """An object that allows only the listed ``properties``; ``required`` ones must be present."""
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _decimal(positive: bool) -> dict[str, Any]:
    number: dict[str, Any] = {"type": "number"}
    if positive:
        number["exclusiveMinimum"] = 0
    pattern = POSITIVE_DECIMAL_PATTERN if positive else DECIMAL_PATTERN
    return {"anyOf": [number, {"type": "string", "pattern": pattern.pattern}]}


def _definitions() -> dict[str, Any]:
    id_schema = {"type": "string", "pattern": ID_PATTERN.pattern}
    name_schema = {"type": "string", "pattern": NAME_PATTERN.pattern}
    timeframe = {"type": "string", "pattern": TIMEFRAME_PATTERN.pattern}
    non_empty = {"type": "string", "minLength": 1}

    price = _closed(
        ["kind", "field"], {"kind": _const("price"), "field": {"enum": list(_PRICE_FIELDS)}}
    )
    constant = _closed(["kind", "value"], {"kind": _const("constant"), "value": _ref("decimal")})
    indicator = _closed(
        ["kind", "name", "version", "params", "source", "timeframe", "output"],
        {
            "kind": _const("indicator"),
            "name": name_schema,
            "version": {"type": "integer", "minimum": 1},
            "params": {
                "type": "object",
                "propertyNames": name_schema,
                "additionalProperties": {"type": ["number", "string"]},
            },
            "source": {"anyOf": [{"type": "null"}, _ref("operand")]},
            "timeframe": timeframe,
            "output": name_schema,
        },
    )

    conditions = {
        "all": _closed(
            ["kind", "of"],
            {"kind": _const("all"), "of": {"type": "array", "minItems": 1, "items": _ref("condition")}},
        ),
        "any": _closed(
            ["kind", "of"],
            {"kind": _const("any"), "of": {"type": "array", "minItems": 1, "items": _ref("condition")}},
        ),
        "not": _closed(["kind", "of"], {"kind": _const("not"), "of": _ref("condition")}),
        "compare": {
            **_closed(
                ["kind", "op", "left", "right"],
                {
                    "kind": _const("compare"),
                    "op": {"enum": list(_COMPARE_OPS)},
                    "left": _ref("operand"),
                    "right": _ref("operand"),
                },
            ),
            # eq is only allowed between constants (never on price/indicator series).
            "if": {"properties": {"op": _const("eq")}, "required": ["op"]},
            "then": {"properties": {"left": _ref("constantOperand"), "right": _ref("constantOperand")}},
        },
        "cross": _closed(
            ["kind", "dir", "left", "right"],
            {
                "kind": _const("cross"),
                "dir": {"enum": ["above", "below"]},
                "left": _ref("operand"),
                "right": _ref("operand"),
            },
        ),
        "edge": _closed(
            ["kind", "dir", "of"],
            {"kind": _const("edge"), "dir": {"enum": ["rising"]}, "of": _ref("condition")},
        ),
    }

    amount = _closed(
        ["unit", "value"],
        {"unit": {"enum": ["fraction_of_open", "sizing_unit"]}, "value": _ref("positiveDecimal")},
    )
    operation_open_close = _closed(
        ["op", "position"], {"op": {"enum": ["open", "close"]}, "position": id_schema}
    )
    operation_scale = _closed(
        ["op", "position", "amount"],
        {"op": {"enum": ["increase", "reduce"]}, "position": id_schema, "amount": _ref("amount")},
    )

    risk_exit = _closed(
        ["kind", "value", "basis"],
        {
            "kind": _const("percent"),
            "value": _ref("positiveDecimal"),
            "basis": _closed(["kind", "leg"], {"kind": _const("leg_price"), "leg": id_schema}),
        },
    )
    leg = {
        **_closed(
            ["id", "instrument", "side", "quantity"],
            {
                "id": id_schema,
                "instrument": _closed(["kind"], {"kind": _const("primary")}),
                "side": {"enum": ["buy", "sell"]},
                "quantity": _ref("positiveDecimal"),
                "role": non_empty,
            },
        ),
    }
    position = {
        **_closed(
            ["role", "hedges", "legs", "sizing"],
            {
                "template": non_empty,
                "role": {"enum": ["core", "hedge"]},
                "hedges": {"anyOf": [{"type": "null"}, id_schema]},
                "legs": {"type": "array", "minItems": 1, "items": _ref("leg")},
                "sizing": _ref("sizing"),
                "risk": _closed(
                    [],
                    {"stop_loss": _ref("riskExit"), "take_profit": _ref("riskExit")},
                ),
            },
        ),
        "allOf": [
            {
                "if": {"properties": {"role": _const("core")}, "required": ["role"]},
                "then": {"properties": {"hedges": {"type": "null"}}},
            },
            {
                "if": {"properties": {"role": _const("hedge")}, "required": ["role"]},
                "then": {"properties": {"hedges": id_schema}},
            },
        ],
    }
    rule = _closed(
        ["id", "when", "then"],
        {
            "id": id_schema,
            "label": non_empty,
            "when": _ref("condition"),
            "then": {"type": "array", "minItems": 1, "items": _ref("operation")},
            "when_position": {
                "type": "object",
                "minProperties": 1,
                "propertyNames": id_schema,
                "additionalProperties": {"enum": ["flat", "open"]},
            },
            "priority": {"type": "integer"},
            "limits": _closed(
                ["max_fires_per_position"],
                {"max_fires_per_position": {"type": "integer", "minimum": 1}},
            ),
        },
    )

    return {
        "decimal": _decimal(positive=False),
        "positiveDecimal": _decimal(positive=True),
        "priceOperand": price,
        "constantOperand": constant,
        "indicatorOperand": indicator,
        "operand": {
            "oneOf": [_ref("priceOperand"), _ref("constantOperand"), _ref("indicatorOperand")]
        },
        **{f"{name}Condition": node for name, node in conditions.items()},
        "condition": {"oneOf": [_ref(f"{name}Condition") for name in conditions]},
        "amount": amount,
        "operation": {"oneOf": [operation_open_close, operation_scale]},
        # V2.0 authorable sizing is explicit share quantity only. percent_of_allocation is
        # produced solely by the V1 adapter and is intentionally absent.
        "sizing": _closed(
            ["unit", "value"], {"unit": _const("shares"), "value": _ref("positiveDecimal")}
        ),
        "riskExit": risk_exit,
        "leg": leg,
        "position": position,
        "rule": rule,
    }


def export_json_schema() -> dict[str, Any]:
    """A fresh, deterministic schema dict (callers may mutate it freely)."""
    return {
        "$schema": JSON_SCHEMA_DIALECT,
        "$id": f"https://algoprofitx.com/schemas/{SCHEMA_ID}/{SCHEMA_VERSION}.json",
        "title": "AlgoProfitX Strategy Definition V2 (authoring schema)",
        "description": NOT_REPRESENTABLE,
        **_closed(
            ["schema", "schema_version", "timeframe", "evaluation", "positions", "rules"],
            {
                "schema": _const(SCHEMA_ID),
                "schema_version": _const(SCHEMA_VERSION),
                "timeframe": {"type": "string", "pattern": TIMEFRAME_PATTERN.pattern},
                "evaluation": {"enum": ["bar_close"]},
                "positions": {
                    "type": "object",
                    "minProperties": 1,
                    "propertyNames": {"type": "string", "pattern": ID_PATTERN.pattern},
                    "additionalProperties": _ref("position"),
                },
                "rules": {"type": "array", "minItems": 1, "items": _ref("rule")},
            },
        ),
        "$defs": _definitions(),
    }


def export_json_schema_text() -> str:
    """Canonical text form: sorted keys, fixed indentation, trailing newline."""
    return json.dumps(export_json_schema(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"
