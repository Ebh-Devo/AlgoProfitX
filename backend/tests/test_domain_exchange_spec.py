"""#50 stage 3: the trading calendar depends on an ORM-free exchange view, not the SQLAlchemy model.

``ExchangeSpec`` and the ``Exchange`` ORM model must be interchangeable wherever a calendar is used, the
calendar's behaviour and error messages must be unchanged, and ``app.market_calendar`` must import with
SQLAlchemy blocked. SQLAlchemy is not removed from the runtime by this stage.
"""

import ast
import dataclasses
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.exchange import ExchangeLike, ExchangeSpec
from app.market_calendar.contracts import CalendarError
from app.market_calendar.reference import IndianReferenceTradingCalendar
from app.models.instrument import Exchange

BACKEND = Path(__file__).resolve().parents[1]
START = datetime(2025, 1, 2, tzinfo=timezone.utc)
END = datetime(2025, 2, 1, tzinfo=timezone.utc)


def orm(code="NSE", zone="Asia/Kolkata", active=True) -> Exchange:
    return Exchange(code=code, timezone=zone, is_active=active)


def spec(code="NSE", zone="Asia/Kolkata", active=True) -> ExchangeSpec:
    return ExchangeSpec(code=code, timezone=zone, is_active=active)


# ----------------------------------------------------------------------------------- the contract


def test_the_spec_is_a_plain_immutable_value_with_exactly_the_calendar_attributes():
    value = spec()
    assert (value.code, value.timezone, value.is_active) == ("NSE", "Asia/Kolkata", True)
    assert [f.name for f in dataclasses.fields(ExchangeSpec)] == ["code", "timezone", "is_active"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.code = "BSE"  # type: ignore[misc]
    assert spec() == spec() and spec() != spec(code="BSE")


def test_both_the_orm_model_and_the_spec_satisfy_the_protocol_attributes():
    for candidate in (orm(), spec()):
        for attribute in ("code", "timezone", "is_active"):
            assert hasattr(candidate, attribute)
    assert {"code", "timezone", "is_active"} <= set(dir(ExchangeLike))


# ------------------------------------------------------- calendar behaviour is identical for both


@pytest.mark.parametrize("code", ["NSE", "BSE"])
def test_sessions_lookup_and_provenance_are_identical_for_the_spec_and_the_orm_model(code):
    calendar = IndianReferenceTradingCalendar()
    from_orm, from_spec = orm(code), spec(code)

    sessions_orm = calendar.sessions_between(from_orm, START, END)
    sessions_spec = calendar.sessions_between(from_spec, START, END)
    assert sessions_spec == sessions_orm and len(sessions_spec) > 15

    instant = sessions_spec[0].open_utc
    assert calendar.session_for(from_spec, instant) == calendar.session_for(from_orm, instant)
    assert calendar.is_trading_instant(from_spec, instant) is True
    assert calendar.provenance(from_spec, sessions_spec) == calendar.provenance(from_orm, sessions_orm)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"active": False}, "Exchange is inactive"),
        ({"code": "XYZ"}, "Exchange is unsupported by the reference calendar"),
        ({"zone": "Not/AZone"}, "Exchange timezone is unknown"),
    ],
)
def test_calendar_refusals_have_the_same_messages_for_the_spec_and_the_orm_model(kwargs, message):
    calendar = IndianReferenceTradingCalendar()
    for build in (orm, spec):
        with pytest.raises(CalendarError) as raised:
            calendar.sessions_between(build(**kwargs), START, END)
        assert str(raised.value) == message


# ------------------------------------------------------------------- SQLAlchemy-blocked import proof

BLOCKED_IMPORT_PROBE = textwrap.dedent(
    """
    import importlib.abc, importlib, sys

    BLOCKED = {"sqlalchemy", "greenlet"}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ImportError("blocked for the SQLAlchemy-free import probe: " + name)
            return None

    sys.meta_path.insert(0, Blocker())

    for name in ("app.domain.exchange", "app.market_calendar", "app.market_calendar.contracts",
                 "app.market_calendar.reference"):
        importlib.import_module(name)

    from app.domain.exchange import ExchangeSpec
    from app.market_calendar import IndianReferenceTradingCalendar
    from datetime import datetime, timezone
    sessions = IndianReferenceTradingCalendar().sessions_between(
        ExchangeSpec("NSE", "Asia/Kolkata", True),
        datetime(2025, 1, 2, tzinfo=timezone.utc), datetime(2025, 1, 10, tzinfo=timezone.utc))
    assert len(sessions) > 3

    print("LOADED=" + repr(sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)))
    print("ORM=" + repr(sorted(m for m in sys.modules if m.startswith(("app.models", "app.db")))))
    """
)


def test_the_market_calendar_works_with_sqlalchemy_blocked():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "TEST_DATABASE_URL", "PERSISTENCE_PROVIDER", "APP_ENV"}
    }
    environment.update(SECRET_KEY="a-long-unique-secret-for-the-calendar-import-probe", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-c", BLOCKED_IMPORT_PROBE],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    lines = result.stdout.strip().splitlines()
    assert lines[-2] == "LOADED=[]" and lines[-1] == "ORM=[]"


def _imports_from(path: Path, prefix: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").startswith(prefix):
            return True
        if isinstance(node, ast.Import) and any(a.name.startswith(prefix) for a in node.names):
            return True
    return False


def test_no_calendar_module_or_catalyst_backtest_service_imports_the_exchange_orm_model():
    calendar_files = sorted((BACKEND / "app" / "market_calendar").rglob("*.py"))
    assert calendar_files
    assert [p.name for p in calendar_files if _imports_from(p, "app.models")] == []
    assert not _imports_from(BACKEND / "app" / "services" / "catalyst_backtest.py", "app.models")
