from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.exchange import ExchangeLike
from app.market_calendar.contracts import CalendarError, SessionType, TradingSession


@dataclass(frozen=True)
class CalendarException:
    exchange_code: str
    local_session_date: date
    session_type: SessionType | None
    local_open: time | None = None
    local_close: time | None = None


# Versioned reference manifest. It intentionally contains no claimed regulatory
# holidays. Future curated data can populate this shape or migrate directly into
# an exchange_calendar_exceptions table without changing the calendar contract.
REFERENCE_EXCEPTION_MANIFEST_VERSION = "indian-reference-exceptions-v1"
REFERENCE_EXCEPTIONS: tuple[CalendarException, ...] = ()


class IndianReferenceTradingCalendar:
    """NSE/BSE weekday reference sessions, not a regulatory holiday calendar."""

    identifier = "indian-cash-reference-calendar"
    policy_version = "v1"
    regular_open = time(9, 15)
    regular_close = time(15, 30)
    supported_exchanges = frozenset({"NSE", "BSE"})

    def __init__(self, exceptions: tuple[CalendarException, ...] = REFERENCE_EXCEPTIONS):
        self._exceptions = {
            (item.exchange_code, item.local_session_date): item for item in exceptions
        }

    def sessions_between(
        self, exchange: ExchangeLike, start: datetime, end: datetime
    ) -> tuple[TradingSession, ...]:
        zone = self._validate(exchange, start)
        self._require_aware(end, "Calendar range end")
        if end < start:
            raise CalendarError("Calendar range end precedes start")
        if end - start > timedelta(days=3660):
            raise CalendarError("Calendar range exceeds its limit")

        first_date = start.astimezone(zone).date()
        last_date = end.astimezone(zone).date()
        start_utc = start.astimezone(timezone.utc)
        end_utc = end.astimezone(timezone.utc)
        sessions: list[TradingSession] = []
        current = first_date
        while current <= last_date:
            session = self._session_on(exchange, current, zone)
            if (
                session is not None
                and session.close_utc >= start_utc
                and session.open_utc <= end_utc
            ):
                sessions.append(session)
            current += timedelta(days=1)
        return tuple(sessions)

    def session_for(
        self, exchange: ExchangeLike, instant: datetime
    ) -> TradingSession | None:
        zone = self._validate(exchange, instant)
        session = self._session_on(exchange, instant.astimezone(zone).date(), zone)
        if session is None:
            return None
        utc_instant = instant.astimezone(timezone.utc)
        return session if session.open_utc <= utc_instant < session.close_utc else None

    def is_trading_instant(self, exchange: ExchangeLike, instant: datetime) -> bool:
        return self.session_for(exchange, instant) is not None

    def provenance(self, exchange: ExchangeLike, sessions: tuple[TradingSession, ...]) -> dict:
        self._validate_exchange(exchange)
        return {
            "calendar_identifier": self.identifier,
            "calendar_policy_version": self.policy_version,
            "exception_manifest_version": REFERENCE_EXCEPTION_MANIFEST_VERSION,
            "exchange_code": exchange.code,
            "exchange_timezone": exchange.timezone,
            "regular_local_open": self.regular_open.isoformat(timespec="minutes"),
            "regular_local_close": self.regular_close.isoformat(timespec="minutes"),
            "session_count": len(sessions),
            "holiday_policy": "weekdays-plus-explicit-reference-exceptions",
        }

    def _session_on(
        self, exchange: ExchangeLike, local_date: date, zone: ZoneInfo
    ) -> TradingSession | None:
        exception = self._exceptions.get((exchange.code, local_date))
        if exception is not None and exception.session_type is None:
            return None
        if exception is None and local_date.weekday() >= 5:
            return None
        session_type = exception.session_type if exception else SessionType.REGULAR
        local_open = (
            exception.local_open
            if exception and exception.local_open
            else self.regular_open
        )
        local_close = (
            exception.local_close
            if exception and exception.local_close
            else self.regular_close
        )
        if local_close <= local_open:
            raise CalendarError("Calendar exception close must follow open")
        open_local = datetime.combine(local_date, local_open, zone)
        close_local = datetime.combine(local_date, local_close, zone)
        return TradingSession(
            local_session_date=local_date,
            open_utc=open_local.astimezone(timezone.utc),
            close_utc=close_local.astimezone(timezone.utc),
            session_type=session_type,
            exchange_code=exchange.code,
        )

    def _validate(self, exchange: ExchangeLike, instant: datetime) -> ZoneInfo:
        self._require_aware(instant, "Calendar instant")
        self._validate_exchange(exchange)
        try:
            return ZoneInfo(exchange.timezone)
        except ZoneInfoNotFoundError as exc:
            raise CalendarError("Exchange timezone is unknown") from exc

    def _validate_exchange(self, exchange: ExchangeLike) -> None:
        if not exchange.is_active:
            raise CalendarError("Exchange is inactive")
        if exchange.code not in self.supported_exchanges:
            raise CalendarError("Exchange is unsupported by the reference calendar")

    @staticmethod
    def _require_aware(value: datetime, label: str) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise CalendarError(f"{label} must be timezone-aware")
