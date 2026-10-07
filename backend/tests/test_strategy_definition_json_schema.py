import copy
import json

import pytest
from jsonschema import Draft202012Validator

from app.strategy_definition import (
    StrategyDefinitionError,
    adapt_v1_definition,
    load_v2_definition,
)
from app.strategy_definition.json_schema import export_json_schema, export_json_schema_text
from tests.test_strategy_definition_v2 import cross, document, ema, position, rsi
from tests.strategy_v2_parity_support import compute_golden


def test_export_succeeds_and_is_valid_json_schema():
    schema = export_json_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["$schema"].endswith("2020-12/schema")
    assert json.loads(export_json_schema_text()) == schema


def test_export_is_deterministic():
    assert export_json_schema_text() == export_json_schema_text()
    assert export_json_schema() == export_json_schema()
    # Callers cannot corrupt later exports by mutating a returned schema.
    first = export_json_schema()
    first["$defs"].clear()
    assert export_json_schema()["$defs"]


def test_required_structures_and_closed_vocabularies():
    schema = export_json_schema()
    defs = schema["$defs"]
    assert schema["required"] == ["schema", "schema_version", "timeframe", "evaluation", "positions", "rules"]
    assert schema["properties"]["schema"] == {"const": "algoprofitx.strategy-definition"}
    assert schema["properties"]["schema_version"] == {"const": 2}
    assert schema["properties"]["evaluation"] == {"enum": ["bar_close"]}
    assert {"position", "leg", "rule", "operation", "condition", "operand", "sizing", "indicatorOperand"} <= set(defs)
    assert defs["leg"]["properties"]["side"] == {"enum": ["buy", "sell"]}
    assert defs["position"]["properties"]["role"] == {"enum": ["core", "hedge"]}
    assert defs["priceOperand"]["properties"]["field"]["enum"] == ["open", "high", "low", "close", "volume"]
    assert defs["compareCondition"]["properties"]["op"]["enum"] == ["gt", "gte", "lt", "lte", "eq"]
    assert defs["indicatorOperand"]["required"] == [
        "kind", "name", "version", "params", "source", "timeframe", "output"
    ]


def test_every_object_is_closed():
    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    found = list(objects(export_json_schema()))
    assert len(found) > 15
    assert all(node["additionalProperties"] is False for node in found)


def test_v1_adapter_only_concepts_do_not_leak():
    text = export_json_schema_text()
    assert "percent_of_allocation" not in text
    assert export_json_schema()["$defs"]["sizing"]["properties"]["unit"] == {"const": "shares"}
    validator = Draft202012Validator(export_json_schema())
    lifted = adapt_v1_definition(
        {"entry": {"type": "ema_crossover", "fast_period": 3, "slow_period": 9}}
    ).to_dict()
    errors = list(validator.iter_errors(lifted))
    assert errors  # the lifted V1 form is not an authorable V2 document
    lifted["positions"]["main"]["sizing"] = {"unit": "shares", "value": 10}
    assert not list(validator.iter_errors(lifted))


def test_golden_lifted_definitions_differ_from_authorable_only_by_sizing():
    validator = Draft202012Validator(export_json_schema())
    for case in compute_golden()["cases"]:
        stored = case["v2_definition"]
        assert validator.is_valid(stored) is False
        stored["positions"]["main"]["sizing"] = {"unit": "shares", "value": 1}
        assert validator.is_valid(stored), case["name"]


def _mutated(mutate):
    doc = document()
    mutate(doc)
    return doc


def _sizing(doc, value):
    doc["positions"]["main"]["sizing"] = value


def _when(doc, node):
    doc["rules"][0]["when"] = node


def _hedge_doc(doc):
    doc["positions"]["floor"] = {**position("put"), "role": "hedge", "hedges": "main"}


# (label, mutation). Each document must be judged identically by schema and loader.
AGREEMENT_CASES = [
    ("base", lambda d: None),
    ("short", lambda d: d["positions"].update(main=position(side="sell"))),
    ("hedge_and_risk", lambda d: (_hedge_doc(d), d["positions"]["main"].update(risk={
        "stop_loss": {"kind": "percent", "value": "2.5", "basis": {"kind": "leg_price", "leg": "stock"}}}))),
    ("nested_tree", lambda d: _when(d, {"kind": "any", "of": [
        {"kind": "all", "of": [cross(), {"kind": "compare", "op": "gt", "left": rsi(14),
                                         "right": {"kind": "constant", "value": -5.5}}]},
        {"kind": "not", "of": {"kind": "edge", "dir": "rising", "of": cross("below")}}]})),
    ("eq_constants", lambda d: _when(d, {"kind": "compare", "op": "eq",
        "left": {"kind": "constant", "value": 1}, "right": {"kind": "constant", "value": "1"}})),
    ("nested_source_5m", lambda d: (d.update(timeframe="5m"), _when(d, {
        "kind": "cross", "dir": "above", "left": ema(3, "5m"), "right": {**ema(9, "5m"), "source": rsi(14)}}))),
    ("null_source", lambda d: _when(d, {"kind": "compare", "op": "gt",
        "left": {**ema(3), "source": None}, "right": {"kind": "constant", "value": 0}})),
    ("optional_rule_fields", lambda d: d["rules"][0].update(
        label="x", priority=-3, when_position={"main": "flat"}, limits={"max_fires_per_position": 2})),
    ("scale_ops", lambda d: d["rules"][0].update(then=[
        {"op": "increase", "position": "main", "amount": {"unit": "sizing_unit", "value": 2}},
        {"op": "reduce", "position": "main", "amount": {"unit": "fraction_of_open", "value": 0.5}}])),
    # --- invalid ---
    ("no_schema", lambda d: d.pop("schema")),
    ("bad_schema", lambda d: d.update(schema="other")),
    ("version_3", lambda d: d.update(schema_version=3)),
    ("version_bool", lambda d: d.update(schema_version=True)),
    ("unknown_top", lambda d: d.update(surprise=1)),
    ("no_positions", lambda d: d.pop("positions")),
    ("empty_positions", lambda d: d.update(positions={})),
    ("empty_rules", lambda d: d.update(rules=[])),
    ("tick_evaluation", lambda d: d.update(evaluation="tick")),
    ("bad_timeframe", lambda d: d.update(timeframe="daily")),
    ("bad_rule_id", lambda d: d["rules"][0].update(id="Bad Id")),
    ("unknown_rule_field", lambda d: d["rules"][0].update(phase="entry")),
    ("unknown_leg_field", lambda d: d["positions"]["main"]["legs"][0].update(order_type="market")),
    ("position_structure", lambda d: d["positions"]["main"].update(position_structure="single_leg")),
    ("bad_side", lambda d: d["positions"]["main"]["legs"][0].update(side="long")),
    ("no_legs", lambda d: d["positions"]["main"].update(legs=[])),
    ("zero_leg_quantity", lambda d: d["positions"]["main"]["legs"][0].update(quantity=0)),
    ("missing_leg_quantity", lambda d: d["positions"]["main"]["legs"][0].pop("quantity")),
    ("string_quantity", lambda d: d["positions"]["main"]["legs"][0].update(quantity="abc")),
    ("signed_string_quantity", lambda d: d["positions"]["main"]["legs"][0].update(quantity="-1")),
    ("bool_quantity", lambda d: d["positions"]["main"]["legs"][0].update(quantity=True)),
    ("no_sizing", lambda d: d["positions"]["main"].pop("sizing")),
    ("zero_sizing", lambda d: _sizing(d, {"unit": "shares", "value": 0})),
    ("percent_sizing", lambda d: _sizing(d, {"unit": "percent_of_allocation", "value": 100})),
    ("contracts_sizing", lambda d: _sizing(d, {"unit": "contracts", "value": 1})),
    ("option_instrument", lambda d: d["positions"]["main"]["legs"][0].update(instrument={"kind": "option"})),
    ("instrument_extra", lambda d: d["positions"]["main"]["legs"][0]["instrument"].update(symbol="TCS")),
    ("core_hedges", lambda d: d["positions"]["main"].update(hedges="main")),
    ("hedge_without_target", lambda d: d["positions"]["main"].update(role="hedge")),
    ("trailing_risk", lambda d: d["positions"]["main"].update(risk={"trailing": {}})),
    ("other_basis", lambda d: d["positions"]["main"].update(risk={
        "stop_loss": {"kind": "percent", "value": 2, "basis": {"kind": "net_premium"}}})),
    ("unknown_op", lambda d: d["rules"][0]["then"][0].update(op="buy")),
    ("replace_op", lambda d: d["rules"][0]["then"][0].update(op="replace")),
    ("closing_side", lambda d: d["rules"][1]["then"][0].update(side="sell")),
    ("empty_then", lambda d: d["rules"][0].update(then=[])),
    ("reduce_no_amount", lambda d: d["rules"][0].update(then=[{"op": "reduce", "position": "main"}])),
    ("open_with_amount", lambda d: d["rules"][0]["then"][0].update(
        amount={"unit": "sizing_unit", "value": 1})),
    ("unknown_condition", lambda d: _when(d, {"kind": "xor", "of": []})),
    ("within_condition", lambda d: _when(d, {"kind": "within", "bars": 3, "of": cross()})),
    ("empty_all", lambda d: _when(d, {"kind": "all", "of": []})),
    ("not_list", lambda d: _when(d, {"kind": "not", "of": [cross()]})),
    ("bad_cross_dir", lambda d: _when(d, {**cross(), "dir": "up"})),
    ("bad_edge_dir", lambda d: _when(d, {"kind": "edge", "dir": "falling", "of": cross()})),
    ("eq_on_series", lambda d: _when(d, {"kind": "compare", "op": "eq", "left": ema(3),
                                         "right": {"kind": "constant", "value": 1}})),
    ("bad_compare_op", lambda d: _when(d, {"kind": "compare", "op": "approx", "left": ema(3), "right": ema(9)})),
    ("bad_price_field", lambda d: _when(d, {"kind": "compare", "op": "gt",
        "left": {"kind": "price", "field": "vwap"}, "right": {"kind": "constant", "value": 1}})),
    ("arith_operand", lambda d: _when(d, {"kind": "compare", "op": "gt",
        "left": {"kind": "arith"}, "right": {"kind": "constant", "value": 1}})),
    ("indicator_no_version", lambda d: d["rules"][0]["when"]["left"].pop("version")),
    ("indicator_version_0", lambda d: d["rules"][0]["when"]["left"].update(version=0)),
    ("indicator_bad_name", lambda d: d["rules"][0]["when"]["left"].update(name="EMA!")),
    ("indicator_params_list", lambda d: d["rules"][0]["when"]["left"].update(params=[3])),
    ("indicator_params_bool", lambda d: d["rules"][0]["when"]["left"].update(params={"period": True})),
    ("indicator_params_nested", lambda d: d["rules"][0]["when"]["left"].update(params={"period": [3]})),
    ("indicator_no_source", lambda d: d["rules"][0]["when"]["left"].pop("source")),
    ("indicator_extra", lambda d: d["rules"][0]["when"]["left"].update(anchor="session")),
    ("indicator_bad_timeframe", lambda d: d["rules"][0]["when"]["left"].update(timeframe="x")),
    ("bad_when_position", lambda d: d["rules"][0].update(when_position={"main": "half"})),
    ("empty_when_position", lambda d: d["rules"][0].update(when_position={})),
    ("bool_priority", lambda d: d["rules"][0].update(priority=True)),
    ("zero_limit", lambda d: d["rules"][0].update(limits={"max_fires_per_position": 0})),
]


def test_schema_and_loader_agree_on_representative_documents():
    validator = Draft202012Validator(export_json_schema())
    disagreements = []
    verdicts = set()
    for label, mutate in AGREEMENT_CASES:
        doc = _mutated(mutate)
        try:
            load_v2_definition(copy.deepcopy(doc))
            loader_ok = True
        except StrategyDefinitionError:
            loader_ok = False
        verdicts.add(loader_ok)
        if validator.is_valid(doc) != loader_ok:
            disagreements.append((label, "loader_ok" if loader_ok else "loader_rejects"))
    assert not disagreements
    assert verdicts == {True, False}  # the corpus exercises both outcomes


def test_loader_only_checks_are_not_claimed_by_the_schema():
    # These need cross-references or counting, which JSON Schema cannot express; the schema
    # documents that and the loader remains authoritative.
    validator = Draft202012Validator(export_json_schema())

    def dangling(d):
        d["rules"][0]["then"][0]["position"] = "ghost"

    def duplicate(d):
        d["rules"][1]["id"] = "enter"

    def big_fraction(d):
        d["rules"][0]["then"] = [
            {"op": "reduce", "position": "main", "amount": {"unit": "fraction_of_open", "value": 1.5}}
        ]

    for mutate in (dangling, duplicate, big_fraction):
        doc = _mutated(mutate)
        assert validator.is_valid(doc)
        with pytest.raises(StrategyDefinitionError):
            load_v2_definition(doc)
    assert "Enforced by the loader only" in export_json_schema()["description"]


def test_trailing_newline_ids_are_rejected_by_the_loader():
    # Python's jsonschema uses re.search, where "$" also matches before a trailing newline,
    # so it would accept this; ECMA engines (and the loader's fullmatch) reject it.
    doc = _mutated(lambda d: d["rules"][0].update(id="enter" + chr(10)))
    with pytest.raises(StrategyDefinitionError):
        load_v2_definition(doc)
