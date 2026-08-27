"""Stable identities for the built-in synthetic reference Instrument."""

import uuid


SYNTHETIC_EQUITY_ID = uuid.UUID("20000000-0000-4000-8000-000000000001")
SYNTHETIC_EQUITY_SYMBOL = "ALGOPROFITX_TEST_EQ"
LEGACY_SYNTHETIC_EQUITY_SYMBOL = "TRADEEBH_TEST_EQ"
SYNTHETIC_EQUITY_SYMBOLS = frozenset(
    (SYNTHETIC_EQUITY_SYMBOL, LEGACY_SYNTHETIC_EQUITY_SYMBOL)
)


def is_synthetic_equity_symbol(value: object) -> bool:
    return isinstance(value, str) and value in SYNTHETIC_EQUITY_SYMBOLS
