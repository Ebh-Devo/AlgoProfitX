"""ORM-free market foundation seed data (exchanges and built-in instruments).

Identifiers and values are persisted and referenced by Catalyst rows and tests; they must not change.
This module must stay free of SQLAlchemy imports. ``app.bootstrap.instruments`` re-exports every name
here and keeps the PostgreSQL seeding code.
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.domain.enums import InstrumentType
from app.instrument_identity import SYNTHETIC_EQUITY_ID, SYNTHETIC_EQUITY_SYMBOL


BOOTSTRAP_VERSION = "phase-2a-v1"

NSE_EXCHANGE_ID = uuid.UUID("10000000-0000-4000-8000-000000000001")
BSE_EXCHANGE_ID = uuid.UUID("10000000-0000-4000-8000-000000000002")
NIFTY_50_INDEX_ID = uuid.UUID("20000000-0000-4000-8000-000000000002")
BANK_NIFTY_INDEX_ID = uuid.UUID("20000000-0000-4000-8000-000000000003")


@dataclass(frozen=True)
class ExchangeSeed:
    id: uuid.UUID
    code: str
    name: str
    country_code: str
    timezone: str
    default_currency: str
    calendar_code: str


@dataclass(frozen=True)
class InstrumentSeed:
    id: uuid.UUID
    exchange_id: uuid.UUID
    canonical_symbol: str
    exchange_symbol: str
    name: str
    instrument_type: InstrumentType
    quote_currency: str
    tick_size: Decimal | None
    lot_size: int | None
    is_tradeable: bool
    is_synthetic: bool = False


EXCHANGES = (
    ExchangeSeed(NSE_EXCHANGE_ID, "NSE", "National Stock Exchange of India", "IN", "Asia/Kolkata", "INR", "XNSE"),
    ExchangeSeed(BSE_EXCHANGE_ID, "BSE", "BSE Limited", "IN", "Asia/Kolkata", "INR", "XBOM"),
)

INSTRUMENTS = (
    InstrumentSeed(
        SYNTHETIC_EQUITY_ID,
        NSE_EXCHANGE_ID,
        SYNTHETIC_EQUITY_SYMBOL,
        SYNTHETIC_EQUITY_SYMBOL,
        "AlgoProfitX Synthetic Reference Equity (not a real security)",
        InstrumentType.EQUITY,
        "INR",
        Decimal("0.01"),
        1,
        True,
        True,
    ),
    InstrumentSeed(
        NIFTY_50_INDEX_ID,
        NSE_EXCHANGE_ID,
        "NSE:NIFTY_50",
        "NIFTY 50",
        "NIFTY 50 Index",
        InstrumentType.INDEX,
        "INR",
        None,
        None,
        False,
    ),
    InstrumentSeed(
        BANK_NIFTY_INDEX_ID,
        NSE_EXCHANGE_ID,
        "NSE:BANK_NIFTY",
        "NIFTY BANK",
        "BANK NIFTY Index",
        InstrumentType.INDEX,
        "INR",
        None,
        None,
        False,
    ),
)
