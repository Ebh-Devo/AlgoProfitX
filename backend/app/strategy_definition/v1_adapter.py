"""V1 -> canonical V2 compatibility adapter.

Lifts a stored V1 configuration into the canonical model *in memory only*; the stored V1
JSON is never touched. V1 semantics are decided by ``app.strategy_rules`` (which the V1
engines also use), so this adapter reuses it rather than re-implementing the legacy
defaults, and makes every default explicit in the resulting definition.

V1 meaning, as lifted:
  * ``entry.action`` is the opening direction of the single leg (buy = long, sell = short).
  * ``entry.direction`` / ``exit.direction`` are the cross directions of the two rules; V1
    does not tie them to the action.
  * ``exit.action`` only had to be the opposite of the entry (V1's single-position check);
    a V2 ``close`` carries no side, so it is validated and dropped.
  * V1 sizes every trade as all of the capital at the entry price, which has no V2-authorable
    equivalent, so the lifted position carries ``percent_of_allocation`` sizing (§7.3).
"""

from decimal import Decimal
from typing import Any

from app.strategy_definition.errors import StrategyDefinitionError, ValidationIssue
from app.strategy_definition.schema import (
    CrossCondition,
    IndicatorRef,
    InstrumentSelector,
    Leg,
    PercentOfAllocationSizing,
    Position,
    PositionOperation,
    PriceOperand,
    Quantity,
    Rule,
    StrategyDefinition,
)
from app.strategy_rules import (
    EmaCrossoverRule,
    StrategyRuleError,
    parse_entry_rule,
    parse_exit_rule,
    require_closing_action,
)

V1_FILL_MODEL = "same_bar_close"
V1_POSITION_ID = "main"
V1_LEG_ID = "stock"


def _ema(period: int, timeframe: str) -> IndicatorRef:
    return IndicatorRef(
        name="ema",
        version=1,
        params={"period": period},
        source=PriceOperand("close"),
        timeframe=timeframe,
        output="value",
    )


def _cross(rule: EmaCrossoverRule, timeframe: str) -> CrossCondition:
    return CrossCondition(
        rule.direction, _ema(rule.fast_period, timeframe), _ema(rule.slow_period, timeframe)
    )


def adapt_v1_definition(configuration: Any, *, timeframe: str = "1d") -> StrategyDefinition:
    """Lift a V1 configuration. ``timeframe`` is V1's backtest-configuration value (default 1d)."""
    if not isinstance(configuration, dict):
        raise StrategyDefinitionError(
            [ValidationIssue("", "invalid_v1_configuration", "a V1 configuration must be an object")]
        )
    try:
        entry = parse_entry_rule(configuration)
        exit_rule = parse_exit_rule(configuration)
        if exit_rule is not None:
            require_closing_action(entry.action, exit_rule.action)
    except StrategyRuleError as exc:
        raise StrategyDefinitionError(
            [ValidationIssue("", "invalid_v1_configuration", str(exc))]
        ) from exc

    rules = [
        Rule(
            id="enter",
            when=_cross(entry, timeframe),
            then=(PositionOperation("open", V1_POSITION_ID),),
        )
    ]
    if exit_rule is not None:
        rules.append(
            Rule(
                id="exit",
                when=_cross(exit_rule, timeframe),
                then=(PositionOperation("close", V1_POSITION_ID),),
            )
        )
    position = Position(
        id=V1_POSITION_ID,
        role="core",
        hedges=None,
        legs=(
            Leg(
                id=V1_LEG_ID,
                instrument=InstrumentSelector(),
                side=entry.action,
                quantity=Quantity(Decimal(1)),
            ),
        ),
        sizing=PercentOfAllocationSizing(Decimal(100)),
    )
    return StrategyDefinition(
        timeframe=timeframe,
        evaluation="bar_close",
        positions=(position,),
        rules=tuple(rules),
    )
