import copy
import json

import pytest

from app.strategy_definition import (
    SCHEMA_ID,
    StrategyDefinitionError,
    detect_schema_version,
    load_definition,
    load_v2_definition,
)
from app.strategy_definition.schema import (
    AllCondition,
    AnyCondition,
    CrossCondition,
    EdgeCondition,
    NotCondition,
)


def ema(period, timeframe="1d"):
    return {
        "kind": "indicator", "name": "ema", "version": 1, "params": {"period": period},
        "source": {"kind": "price", "field": "close"}, "timeframe": timeframe, "output": "value",
    }


def rsi(period):
    return {**ema(period), "name": "rsi"}


def leg(leg_id="stock", side="buy"):
    return {"id": leg_id, "instrument": {"kind": "primary"}, "side": side, "quantity": 1}


def position(leg_id="stock", side="buy", **extra):
    return {
        "role": "core", "hedges": None, "legs": [leg(leg_id, side)],
        "sizing": {"unit": "shares", "value": 10}, **extra,
    }


def cross(direction="above"):
    return {"kind": "cross", "dir": direction, "left": ema(3), "right": ema(9)}


def document(**overrides):
    doc = {
        "schema": SCHEMA_ID, "schema_version": 2, "timeframe": "1d", "evaluation": "bar_close",
        "positions": {"main": position()},
        "rules": [
            {"id": "enter", "when": cross("above"), "then": [{"op": "open", "position": "main"}]},
            {"id": "exit", "when": cross("below"), "then": [{"op": "close", "position": "main"}]},
        ],
    }
    doc.update(overrides)
    return doc


def codes(doc):
    with pytest.raises(StrategyDefinitionError) as info:
        load_v2_definition(doc)
    return {(issue.path, issue.code) for issue in info.value.issues}


# --- valid documents ---------------------------------------------------------------------


def test_minimal_long_loads_and_round_trips():
    doc = document()
    definition = load_v2_definition(doc)
    assert definition.positions[0].legs[0].side == "buy"
    assert definition.timeframe == "1d" and definition.evaluation == "bar_close"
    assert definition.to_dict() == doc
    assert load_v2_definition(json.loads(json.dumps(definition.to_dict()))) == definition


def test_minimal_short_loads():
    doc = document(positions={"main": position(side="sell")})
    assert load_v2_definition(doc).positions[0].legs[0].side == "sell"


def test_multiple_legs_structurally_valid():
    legs = [leg("first", "buy"), leg("second", "sell")]
    doc = document(positions={"main": {**position(), "legs": legs}})
    assert [item.id for item in load_v2_definition(doc).positions[0].legs] == ["first", "second"]


def test_multiple_positions_hedge_and_risk():
    doc = document(
        positions={
            "main": position(risk={
                "stop_loss": {"kind": "percent", "value": "2.5", "basis": {"kind": "leg_price", "leg": "stock"}},
                "take_profit": {"kind": "percent", "value": 5, "basis": {"kind": "leg_price", "leg": "stock"}},
            }),
            "floor": {**position("put"), "role": "hedge", "hedges": "main"},
        },
    )
    definition = load_v2_definition(doc)
    assert str(definition.positions[0].risk.stop_loss.value) == "2.5"
    assert definition.to_dict() == doc


def test_multiple_rules_with_optional_fields():
    doc = document()
    doc["rules"][0].update(
        label="Buy", priority=10, when_position={"main": "flat"}, limits={"max_fires_per_position": 1}
    )
    doc["rules"].append(
        {"id": "trim", "when": cross(), "then": [
            {"op": "reduce", "position": "main", "amount": {"unit": "fraction_of_open", "value": "0.5"}},
            {"op": "increase", "position": "main", "amount": {"unit": "sizing_unit", "value": 2}},
        ]}
    )
    definition = load_v2_definition(doc)
    assert len(definition.rules) == 3
    assert definition.to_dict() == doc


def test_nested_condition_tree():
    tree = {"kind": "any", "of": [
        {"kind": "all", "of": [
            cross(),
            {"kind": "compare", "op": "gt", "left": rsi(14), "right": {"kind": "constant", "value": 50}},
        ]},
        {"kind": "not", "of": {"kind": "compare", "op": "lte", "left": {"kind": "price", "field": "volume"},
                               "right": {"kind": "constant", "value": "1000.5"}}},
        {"kind": "edge", "dir": "rising", "of": cross("below")},
    ]}
    doc = document()
    doc["rules"][0]["when"] = tree
    when = load_v2_definition(doc).rules[0].when
    assert isinstance(when, AnyCondition)
    assert isinstance(when.of[0], AllCondition) and isinstance(when.of[0].of[0], CrossCondition)
    assert isinstance(when.of[1], NotCondition) and isinstance(when.of[2], EdgeCondition)
    assert load_v2_definition(doc).to_dict() == doc


def test_explicit_timeframe_and_nested_indicator_source():
    nested = {**ema(9, "5m"), "source": rsi(14)}
    doc = document(timeframe="5m")
    doc["rules"][0]["when"] = {"kind": "cross", "dir": "above", "left": ema(3, "5m"), "right": nested}
    definition = load_v2_definition(doc)
    assert definition.timeframe == "5m"
    assert definition.rules[0].when.right.source.name == "rsi"


def test_no_catalog_knowledge_in_loader():
    doc = document()
    doc["rules"][0]["when"] = {
        "kind": "compare", "op": "gt",
        "left": {**ema(3), "name": "made_up_indicator", "output": "anything"},
        "right": {"kind": "constant", "value": 1},
    }
    assert load_v2_definition(doc).rules[0].when.left.name == "made_up_indicator"


# --- invalid documents -------------------------------------------------------------------


def test_missing_schema_and_wrong_version():
    doc = document()
    del doc["schema"]
    assert ("schema", "missing_field") in codes(doc)
    assert ("schema", "invalid_schema") in codes(document(schema="other"))
    assert ("schema_version", "unsupported_schema_version") in codes(document(schema_version=3))
    assert ("schema_version", "unsupported_schema_version") in codes(document(schema_version=True))
    assert ("schema_version", "unsupported_schema_version") in codes(document(schema_version="2"))
    assert ("", "invalid_document") in codes([])


@pytest.mark.parametrize("field", ["timeframe", "evaluation", "positions", "rules"])
def test_missing_required_top_level_fields(field):
    doc = document()
    del doc[field]
    assert (field, "missing_field") in codes(doc)


def test_missing_nested_required_fields():
    doc = document()
    del doc["positions"]["main"]["legs"][0]["side"]
    del doc["rules"][0]["then"]
    found = codes(doc)
    assert ("positions.main.legs[0].side", "missing_field") in found
    assert ("rules[0].then", "missing_field") in found
    doc = document()
    del doc["positions"]["main"]["hedges"]
    assert codes(doc) == {("positions.main.hedges", "missing_field")}


def test_unknown_structural_fields_rejected_everywhere():
    doc = document(surprise=1)
    assert codes(doc) == {("surprise", "unknown_field")}
    doc = document()
    doc["positions"]["main"]["position_structure"] = "single_leg"
    assert codes(doc) == {("positions.main.position_structure", "unknown_field")}
    doc = document()
    doc["positions"]["main"]["legs"][0]["order_type"] = "market"
    doc["rules"][0]["phase"] = "entry"
    doc["rules"][1]["when"]["extra"] = True
    found = codes(doc)
    assert ("positions.main.legs[0].order_type", "unknown_field") in found
    assert ("rules[0].phase", "unknown_field") in found
    assert ("rules[1].when.extra", "unknown_field") in found


def test_closing_side_on_action_rejected():
    doc = document()
    doc["rules"][1]["then"][0]["side"] = "sell"
    assert ("rules[1].then[0].side", "unknown_field") in codes(doc)


def test_duplicate_ids_share_one_namespace():
    doc = document()
    doc["rules"][1]["id"] = "enter"
    assert ("rules[1]", "duplicate_id") in codes(doc)
    doc = document()
    doc["rules"][0]["id"] = "stock"  # collides with the leg id
    assert ("rules[0]", "duplicate_id") in codes(doc)
    doc = document(positions={"main": {**position(), "legs": [leg("a"), leg("a")]}})
    assert ("positions.main.legs[1]", "duplicate_id") in codes(doc)


@pytest.mark.parametrize("bad_id", ["", "Upper", "has space", "-lead", "x" * 65, 5])
def test_invalid_ids(bad_id):
    doc = document()
    doc["rules"][0]["id"] = bad_id
    assert ("rules[0].id", "invalid_id") in codes(doc)


def test_invalid_operation():
    doc = document()
    doc["rules"][0]["then"][0]["op"] = "buy"
    assert ("rules[0].then[0].op", "unknown_kind") in codes(doc)
    doc["rules"][0]["then"][0]["op"] = "replace"
    assert ("rules[0].then[0].op", "unsupported_kind") in codes(doc)
    doc["rules"][0]["then"][0] = {"op": "close", "position": "ghost"}
    assert ("rules[0].then[0].position", "unknown_reference") in codes(doc)
    doc["rules"][0]["then"] = []
    assert ("rules[0].then", "invalid_rule") in codes(doc)


def test_increase_reduce_amount_rules():
    doc = document()
    doc["rules"][0]["then"] = [{"op": "reduce", "position": "main"}]
    assert ("rules[0].then[0].amount", "missing_field") in codes(doc)
    doc["rules"][0]["then"] = [
        {"op": "reduce", "position": "main", "amount": {"unit": "fraction_of_open", "value": 1.5}}
    ]
    assert ("rules[0].then[0].amount.value", "invalid_amount") in codes(doc)
    doc["rules"][0]["then"] = [{"op": "open", "position": "main", "amount": {"unit": "sizing_unit", "value": 1}}]
    assert ("rules[0].then[0].amount", "unknown_field") in codes(doc)


def test_invalid_condition_nodes():
    doc = document()
    for bad, code in [
        ({"kind": "xor", "of": []}, "unknown_kind"),
        ({"kind": "within", "bars": 3, "of": cross()}, "unsupported_kind"),
        ({"kind": "all", "of": []}, "invalid_condition"),
        ({"kind": "not", "of": [cross()]}, "invalid_type"),
        ({"kind": "cross", "dir": "up", "left": ema(3), "right": ema(9)}, "invalid_value"),
        ({"kind": "edge", "dir": "falling", "of": cross()}, "invalid_value"),
        ({"kind": "compare", "op": "eq", "left": ema(3), "right": {"kind": "constant", "value": 1}}, "invalid_condition"),
        ({"kind": "compare", "op": "approx", "left": ema(3), "right": ema(9)}, "invalid_value"),
        ({"dir": "above"}, "missing_field"),
        ("cross", "invalid_type"),
    ]:
        doc["rules"][0]["when"] = bad
        assert any(c == code for _, c in codes(doc)), bad


def test_condition_depth_is_bounded():
    node = cross()
    for _ in range(40):
        node = {"kind": "not", "of": node}
    doc = document()
    doc["rules"][0]["when"] = node
    assert any(code == "max_depth_exceeded" for _, code in codes(doc))


def test_missing_and_invalid_quantity():
    doc = document()
    del doc["positions"]["main"]["sizing"]
    assert ("positions.main.sizing", "missing_field") in codes(doc)
    for value in [0, -1, "abc", None, True, [1], float("inf")]:
        doc = document()
        doc["positions"]["main"]["sizing"]["value"] = value
        assert ("positions.main.sizing.value", "invalid_quantity") in codes(doc), value
    doc = document()
    doc["positions"]["main"]["legs"][0]["quantity"] = 0
    assert ("positions.main.legs[0].quantity", "invalid_quantity") in codes(doc)
    del doc["positions"]["main"]["legs"][0]["quantity"]
    assert ("positions.main.legs[0].quantity", "missing_field") in codes(doc)


def test_sizing_units_are_gated():
    doc = document()
    doc["positions"]["main"]["sizing"] = {"unit": "percent_of_allocation", "value": 100}
    assert ("positions.main.sizing.unit", "sizing_not_authorable") in codes(doc)
    doc["positions"]["main"]["sizing"] = {"unit": "contracts", "value": 1}
    assert ("positions.main.sizing.unit", "unsupported_kind") in codes(doc)
    doc["positions"]["main"]["sizing"] = {"unit": "furlongs", "value": 1}
    assert ("positions.main.sizing.unit", "unknown_kind") in codes(doc)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda i: i.pop("name"),
        lambda i: i.update(name="EMA!"),
        lambda i: i.update(version=0),
        lambda i: i.update(version=1.5),
        lambda i: i.update(params=[3]),
        lambda i: i.update(params={"period": [3]}),
        lambda i: i.update(params={"period": True}),
        lambda i: i.update(timeframe="daily"),
        lambda i: i.update(output=""),
        lambda i: i.update(source={"kind": "price", "field": "vwap"}),
        lambda i: i.pop("source"),
        lambda i: i.update(unexpected=1),
    ],
)
def test_malformed_indicator_reference(mutate):
    doc = document()
    indicator = doc["rules"][0]["when"]["left"]
    mutate(indicator)
    assert any(path.startswith("rules[0].when.left") for path, _ in codes(doc))


def test_invalid_instrument_selector():
    doc = document()
    doc["positions"]["main"]["legs"][0]["instrument"] = {"kind": "option"}
    assert ("positions.main.legs[0].instrument.kind", "unsupported_kind") in codes(doc)
    doc["positions"]["main"]["legs"][0]["instrument"] = {"kind": "primary", "symbol": "TCS"}
    assert ("positions.main.legs[0].instrument.symbol", "unknown_field") in codes(doc)
    doc["positions"]["main"]["legs"][0]["instrument"] = {"kind": "broker_token"}
    assert ("positions.main.legs[0].instrument.kind", "unknown_kind") in codes(doc)
    doc["positions"]["main"]["legs"][0]["instrument"] = {}
    assert ("positions.main.legs[0].instrument.kind", "missing_field") in codes(doc)


def test_invalid_position_leg_relationships():
    doc = document()
    doc["positions"]["main"]["legs"] = []
    assert ("positions.main.legs", "invalid_position") in codes(doc)

    doc = document()
    doc["positions"]["main"]["hedges"] = "main"
    assert ("positions.main.hedges", "invalid_position") in codes(doc)

    doc = document()
    doc["positions"]["main"]["role"] = "hedge"
    assert ("positions.main.hedges", "invalid_position") in codes(doc)

    doc = document(positions={"main": position(), "floor": {**position("put"), "role": "hedge", "hedges": "ghost"}})
    assert ("positions.floor.hedges", "unknown_reference") in codes(doc)

    doc = document()
    doc["positions"]["main"]["risk"] = {
        "stop_loss": {"kind": "percent", "value": 2, "basis": {"kind": "leg_price", "leg": "nope"}}
    }
    assert ("positions.main.risk.stop_loss.basis.leg", "unknown_reference") in codes(doc)
    doc["positions"]["main"]["risk"] = {"trailing": {}}
    assert ("positions.main.risk.trailing", "unsupported_kind") in codes(doc)
    doc["positions"]["main"]["risk"] = {
        "stop_loss": {"kind": "percent", "value": 2, "basis": {"kind": "net_premium"}}
    }
    assert ("positions.main.risk.stop_loss.basis.kind", "unsupported_kind") in codes(doc)

    doc = document()
    doc["rules"][0]["when_position"] = {"ghost": "flat"}
    assert ("rules[0].when_position.ghost", "unknown_reference") in codes(doc)
    doc["rules"][0]["when_position"] = {"main": "half"}
    assert ("rules[0].when_position.main", "invalid_value") in codes(doc)


def test_empty_positions_and_rules_rejected():
    assert ("positions", "invalid_type") in codes(document(positions={}))
    assert ("rules", "invalid_type") in codes(document(rules=[]))


def test_all_issues_are_reported_deterministically():
    doc = document()
    doc["rules"][0]["id"] = "Bad"
    doc["positions"]["main"]["sizing"]["value"] = 0
    first = codes(doc)
    assert len(first) >= 2
    with pytest.raises(StrategyDefinitionError) as a:
        load_v2_definition(doc)
    with pytest.raises(StrategyDefinitionError) as b:
        load_v2_definition(copy.deepcopy(doc))
    assert a.value.issues == b.value.issues
    assert {issue.severity for issue in a.value.issues} == {"error"}
    assert set(a.value.issues[0].to_dict()) == {"path", "code", "message", "severity"}


def test_loader_does_not_mutate_input():
    doc = document()
    snapshot = copy.deepcopy(doc)
    load_v2_definition(doc)
    assert doc == snapshot


# --- version detection -------------------------------------------------------------------


def test_detection_is_explicit():
    assert detect_schema_version({"entry": {"type": "ema_crossover"}}) == 1
    assert detect_schema_version({}) == 1
    assert detect_schema_version(document()) == 2
    assert detect_schema_version({"schema_version": 2}) == 2
    # V2-looking structure without the markers is not V2.
    assert detect_schema_version({"positions": {}, "rules": []}) == 1
    with pytest.raises(StrategyDefinitionError):
        detect_schema_version([])


def test_load_definition_dispatches():
    loaded = load_definition(document())
    assert loaded.source_schema_version == 2 and loaded.fill_model is None
    with pytest.raises(StrategyDefinitionError):
        load_definition({"schema_version": 3})
    with pytest.raises(StrategyDefinitionError):
        load_definition({"positions": {}, "rules": []})  # not V2 and not a valid V1
