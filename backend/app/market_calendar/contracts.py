import enum
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, Sequence

from app.models.instrument import Exchange


class SessionType(str, enum.Enum):
    REGULAR = "regular"
    SHORTENED = "shortened"
    SPECIAL = "special"


@dataclass(frozen=True)
class TradingSession:
    local_session_date: date
    open_utc: datetime
    close_utc: datetime
    session_type: SessionType
    exchange_code: str


class TradingCalendar(Protocol):
    identifier: str
    policy_version: str

    def sessions_between(
        self, exchange: Exchange, start: datetime, end: datetime
    ) -> Sequence[TradingSession]: ...

    def session_for(
        self, exchange: Exchange, instant: datetime
    ) -> TradingSession | None: ...

    def is_trading_instant(self, exchange: Exchange, instant: datetime) -> bool: ...


class CalendarError(ValueError):
    """A deterministic calendar validation failure safe for API results."""
