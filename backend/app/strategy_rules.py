"""Domain validation for the V1 strategy rule configuration.

V1 is intentionally limited: one EMA-crossover entry rule and one optional EMA-crossover
exit rule, trading a single position. ``action`` is the order side (buy/sell) and is *not*
a synonym for long/short: the entry action decides which side the position takes. A future
strategy-definition architecture (multi-leg strategies such as straddles and strangles,
hedging, partial exits, other indicators, AND/OR condition trees) will replace this; nothing
here should be extended towards that.

This module is independent of any concrete backtest engine so schemas and engines can both
depend on it.
"""

from dataclasses import dataclass
from typing import Any, Literal

Action = Literal["buy", "sell"]
Direction = Literal["above", "below"]

ACTIONS = ("buy", "sell")
DIRECTIONS = ("above", "below")
EMA_CROSSOVER = "ema_crossover"

# Configurations stored before actions existed: entry buys on a cross above, exit sells
# on a cross below.
LEGACY_ENTRY_ACTION: Action = "buy"
LEGACY_ENTRY_DIRECTION: Direction = "above"
LEGACY_EXIT_ACTION: Action = "sell"
LEGACY_EXIT_DIRECTION: Direction = "below"


class StrategyRuleError(ValueError):
    """A strategy rule configuration is invalid."""


@dataclass(frozen=True)
class EmaCrossoverRule:
    action: Action
    direction: Direction
    fast_period: int
    slow_period: int


def _choice(rule: dict, key: str, allowed: tuple[str, ...], default: str, label: str) -> str:
    value = rule.get(key, default)
    if value not in allowed:
        raise StrategyRuleError(f"{label}.{key} must be one of: {', '.join(allowed)}")
    return value


def _periods(rule: dict, label: str) -> tuple[int, int]:
    try:
        fast_period = int(rule["fast_period"])
        slow_period = int(rule["slow_period"])
    except (KeyError, TypeError, ValueError) as exc:
        raise StrategyRuleError(f"{label} EMA periods must be positive integers") from exc
    if fast_period <= 0 or slow_period <= fast_period:
        raise StrategyRuleError(f"{label} EMA periods must satisfy 0 < fast < slow")
    return fast_period, slow_period


def _rule(configuration: dict, key: str, default_action: str, default_direction: str) -> EmaCrossoverRule:
    rule = configuration.get(key)
    if not isinstance(rule, dict) or rule.get("type") != EMA_CROSSOVER:
        raise StrategyRuleError(f"Reference engine supports only {key}.type={EMA_CROSSOVER}")
    action = _choice(rule, "action", ACTIONS, default_action, key)
    direction = _choice(rule, "direction", DIRECTIONS, default_direction, key)
    fast_period, slow_period = _periods(rule, key.capitalize())
    return EmaCrossoverRule(action, direction, fast_period, slow_period)  # type: ignore[arg-type]


def parse_entry_rule(configuration: dict) -> EmaCrossoverRule:
    return _rule(configuration, "entry", LEGACY_ENTRY_ACTION, LEGACY_ENTRY_DIRECTION)


def parse_exit_rule(configuration: dict) -> EmaCrossoverRule | None:
    """The exit rule, or None for entry-only (including legacy) configurations."""
    if "exit" not in configuration:
        return None
    return _rule(configuration, "exit", LEGACY_EXIT_ACTION, LEGACY_EXIT_DIRECTION)


def require_closing_action(entry_action: str, exit_action: str) -> None:
    """V1 trades one position: the exit must close it, so it takes the opposite side."""
    if exit_action == entry_action:
        raise StrategyRuleError(
            "Exit action must be the opposite of the entry action: V1 holds a single position"
        )


def validate_rule_configuration(configuration: dict[str, Any]) -> None:
    """Cheap structural checks run when a Version is created.

    Entry periods are validated by the engine at run time (as before); here the entry's
    action/direction and the whole exit rule are checked, plus that exit closes the entry.
    """
    entry = configuration.get("entry")
    entry_action: str = LEGACY_ENTRY_ACTION
    if isinstance(entry, dict) and entry.get("type") == EMA_CROSSOVER:
        entry_action = _choice(entry, "action", ACTIONS, LEGACY_ENTRY_ACTION, "entry")
        _choice(entry, "direction", DIRECTIONS, LEGACY_ENTRY_DIRECTION, "entry")
    exit_rule = parse_exit_rule(configuration)
    if exit_rule is not None:
        require_closing_action(entry_action, exit_rule.action)
