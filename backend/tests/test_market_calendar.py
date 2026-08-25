from datetime import date, datetime, time, timezone

import pytest

from app.market_calendar.contracts import CalendarError, SessionType
from app.market_calendar.reference import CalendarException, IndianReferenceTradingCalendar
from app.models.instrument import Exchange


def exchange(code: str = "NSE", *, active: bool = True, zone: str = "Asia/Kolkata") -> Exchange:
    return Exchange(code=code, timezone=zone, is_active=active)


@pytest.mark.parametrize("code", ["NSE", "BSE"])
def test_regular_indian_session_uses_exchange_local_wall_time(code):
    calendar = IndianReferenceTradingCalendar()
    session = calendar.sessions_between(
        exchange(code),
        datetime(2025, 1, 2, tzinfo=timezone.utc),
        datetime(2025, 1, 3, tzinfo=timezone.utc),
    )[0]

    assert session.local_session_date == date(2025, 1, 2)
    assert session.open_utc == datetime(2025, 1, 2, 3, 45, tzinfo=timezone.utc)
    assert session.close_utc == datetime(2025, 1, 2, 10, 0, tzinfo=timezone.utc)
    assert session.session_type == SessionType.REGULAR
    assert session.exchange_code == code


def test_session_lookup_excludes_weekends_and_outside_session_instants():
    calendar = IndianReferenceTradingCalendar()
    nse = exchange()

    assert calendar.is_trading_instant(nse, datetime(2025, 1, 3, 3, 45, tzinfo=timezone.utc))
    assert not calendar.is_trading_instant(nse, datetime(2025, 1, 3, 3, 44, tzinfo=timezone.utc))
    assert not calendar.is_trading_instant(nse, datetime(2025, 1, 3, 10, 0, tzinfo=timezone.utc))
    assert calendar.session_for(nse, datetime(2025, 1, 4, 5, 0, tzinfo=timezone.utc)) is None


def test_naive_inactive_unknown_and_invalid_timezone_inputs_fail_clearly():
    calendar = IndianReferenceTradingCalendar()
    with pytest.raises(CalendarError, match="timezone-aware"):
        calendar.session_for(exchange(), datetime(2025, 1, 2, 9, 15))
    with pytest.raises(CalendarError, match="inactive"):
        calendar.session_for(exchange(active=False), datetime(2025, 1, 2, tzinfo=timezone.utc))
    with pytest.raises(CalendarError, match="unsupported"):
        calendar.session_for(exchange("UNKNOWN"), datetime(2025, 1, 2, tzinfo=timezone.utc))
    with pytest.raises(CalendarError, match="timezone is unknown"):
        calendar.session_for(exchange(zone="Invalid/Zone"), datetime(2025, 1, 2, tzinfo=timezone.utc))


def test_explicit_closed_shortened_and_special_exceptions_are_representable():
    calendar = IndianReferenceTradingCalendar(
        (
            CalendarException("NSE", date(2025, 1, 6), None),
            CalendarException("NSE", date(2025, 1, 7), SessionType.SHORTENED, local_close=time(12, 0)),
            CalendarException("NSE", date(2025, 1, 11), SessionType.SPECIAL, time(18, 0), time(19, 0)),
        )
    )
    nse = exchange()

    assert calendar.session_for(nse, datetime(2025, 1, 6, 5, 0, tzinfo=timezone.utc)) is None
    shortened = calendar.sessions_between(nse, datetime(2025, 1, 7, tzinfo=timezone.utc), datetime(2025, 1, 8, tzinfo=timezone.utc))[0]
    assert shortened.session_type == SessionType.SHORTENED
    assert shortened.close_utc == datetime(2025, 1, 7, 6, 30, tzinfo=timezone.utc)
    special = calendar.sessions_between(nse, datetime(2025, 1, 11, tzinfo=timezone.utc), datetime(2025, 1, 12, tzinfo=timezone.utc))[0]
    assert special.session_type == SessionType.SPECIAL
