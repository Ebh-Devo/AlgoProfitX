"""Small typed-definition builders shared by the Phase 4 validator and capability tests."""

from decimal import Decimal

from app.strategy_definition.schema import (
    CompareCondition,
    ConstantOperand,
    CrossCondition,
    IndicatorRef,
    InstrumentSelector,
    Leg,
    LegPriceBasis,
    Position,
    PositionOperation,
    PriceOperand,
    Quantity,
    RiskDefinition,
    RiskExit,
    Rule,
    SharesSizing,
    StrategyDefinition,
)

D = Decimal
CLOSE = PriceOperand("close")


def ind(name="ema", period=9, timeframe="1d", source=CLOSE, version=1, output="value"):
    return IndicatorRef(name, version, {"period": period}, source, timeframe, output)


def leg(leg_id="stock", side="buy", quantity="1"):
    return Leg(leg_id, InstrumentSelector(), side, Quantity(D(quantity)))


def position(
    position_id="main", role="core", hedges=None, legs=None, sizing=None, risk=None
) -> Position:
    return Position(
        position_id,
        role,
        hedges,
        tuple(legs if legs is not None else [leg()]),
        sizing or SharesSizing(D(10)),
        None,
        risk,
    )


def stop(value="2", leg_id="stock") -> RiskExit:
    return RiskExit(D(value), LegPriceBasis(leg_id))


def op(kind="open", position_id="main", amount=None) -> PositionOperation:
    return PositionOperation(kind, position_id, amount)


def rule(rule_id="r", when=None, then=None, **kwargs) -> Rule:
    when = when or CompareCondition("gt", CLOSE, ConstantOperand(D(1)))
    return Rule(rule_id, when, tuple([op()] if then is None else then), **kwargs)


def ema_cross() -> CrossCondition:
    return CrossCondition("above", ind("ema", 9), ind("ema", 21))


def long_definition(**changes) -> StrategyDefinition:
    """Long EMA crossover: open on cross up, close on cross down."""
    fields = dict(
        timeframe="1d",
        evaluation="bar_close",
        positions=(position(),),
        rules=(
            rule("enter", ema_cross(), [op("open")]),
            rule(
                "exit",
                CrossCondition("below", ind("ema", 9), ind("ema", 21)),
                [op("close")],
            ),
        ),
    )
    fields.update(changes)
    return StrategyDefinition(**fields)
