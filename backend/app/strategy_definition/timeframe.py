"""Timeframe arithmetic shared by validation and capability derivation (spec §17)."""

from app.strategy_definition.loader import TIMEFRAME_PATTERN

_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440, "w": 10080}
_INTRADAY_UNITS = ("m", "h")


def timeframe_minutes(timeframe: str) -> int | None:
    """Length of a timeframe in minutes, or ``None`` if it is not a well-formed timeframe."""
    if not isinstance(timeframe, str) or not TIMEFRAME_PATTERN.fullmatch(timeframe):
        return None
    return int(timeframe[:-1]) * _UNIT_MINUTES[timeframe[-1]]


def is_intraday(timeframe: str) -> bool:
    """True for minute/hour timeframes. Malformed timeframes are not intraday."""
    return timeframe_minutes(timeframe) is not None and timeframe[-1] in _INTRADAY_UNITS
