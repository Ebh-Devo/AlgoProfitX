"""#50 stage 2: the V2 execution guard and the market seed data live in ORM-free domain modules.

The legacy import paths (``app.services.strategy``, ``app.bootstrap.instruments``) must keep resolving to
the very same objects, the V2 fail-closed contract must be unchanged, and ``app.persistence.catalyst``
must import with SQLAlchemy blocked. SQLAlchemy is **not** removed from the runtime by this stage.
"""

import ast
import os
import subprocess
import sys
import textwrap
import uuid
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.bootstrap.instruments as legacy_seed
import app.domain.execution_support as support
import app.domain.market_seed as seed
import app.services.strategy as legacy_strategy
from app.domain.enums import InstrumentType

BACKEND = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------- V2 execution-support guard


def test_legacy_strategy_module_re_exports_the_same_guard_objects():
    for name in (
        "UnsupportedExecutionVersionError",
        "require_execution_supported",
        "UNSUPPORTED_EXECUTION_VERSION_CODE",
        "V1_SCHEMA_VERSION",
    ):
        assert getattr(legacy_strategy, name) is getattr(support, name)
    # An ``except`` written against the old path still catches the error raised by the new module.
    with pytest.raises(legacy_strategy.UnsupportedExecutionVersionError):
        support.require_execution_supported(SimpleNamespace(definition_schema_version=2), "publish")


def test_the_guard_contract_is_unchanged():
    assert support.V1_SCHEMA_VERSION == 1
    assert support.UNSUPPORTED_EXECUTION_VERSION_CODE == "strategy_definition_version_unsupported_for_execution"
    assert issubclass(support.UnsupportedExecutionVersionError, ValueError)

    # No version, an unset schema version and V1 are all permitted.
    support.require_execution_supported(None, "publish")
    support.require_execution_supported(SimpleNamespace(), "publish")
    support.require_execution_supported(SimpleNamespace(definition_schema_version=None), "publish")
    support.require_execution_supported(SimpleNamespace(definition_schema_version=1), "publish")

    for version in (2, 3, 0, "2"):
        with pytest.raises(support.UnsupportedExecutionVersionError) as raised:
            support.require_execution_supported(SimpleNamespace(definition_schema_version=version), "deploy")
        error = raised.value
        assert error.code == "strategy_definition_version_unsupported_for_execution"
        assert error.message == (
            f"Cannot deploy: strategy definition schema version {version!r} is not supported by the current "
            "execution environment. Version 2 definitions can be backtested only."
        )
        assert error.detail() == {"code": error.code, "message": error.message}
        assert str(error) == error.message


# ------------------------------------------------------------------------------- market seed data


def test_legacy_bootstrap_module_re_exports_the_same_seed_objects():
    for name in (
        "BOOTSTRAP_VERSION",
        "NSE_EXCHANGE_ID",
        "BSE_EXCHANGE_ID",
        "NIFTY_50_INDEX_ID",
        "BANK_NIFTY_INDEX_ID",
        "EXCHANGES",
        "INSTRUMENTS",
        "ExchangeSeed",
        "InstrumentSeed",
    ):
        assert getattr(legacy_seed, name) is getattr(seed, name)
    assert legacy_seed.InstrumentType is InstrumentType
    # Re-exports other code and tests import from the legacy module.
    assert legacy_seed.SYNTHETIC_EQUITY_ID == uuid.UUID("20000000-0000-4000-8000-000000000001")


def test_seed_values_are_frozen():
    assert seed.BOOTSTRAP_VERSION == "phase-2a-v1"
    assert str(seed.NSE_EXCHANGE_ID) == "10000000-0000-4000-8000-000000000001"
    assert str(seed.BSE_EXCHANGE_ID) == "10000000-0000-4000-8000-000000000002"
    assert str(seed.NIFTY_50_INDEX_ID) == "20000000-0000-4000-8000-000000000002"
    assert str(seed.BANK_NIFTY_INDEX_ID) == "20000000-0000-4000-8000-000000000003"

    assert [(e.code, e.country_code, e.timezone, e.default_currency, e.calendar_code) for e in seed.EXCHANGES] == [
        ("NSE", "IN", "Asia/Kolkata", "INR", "XNSE"),
        ("BSE", "IN", "Asia/Kolkata", "INR", "XBOM"),
    ]
    assert [
        (
            i.canonical_symbol,
            i.exchange_symbol,
            i.instrument_type,
            i.quote_currency,
            i.tick_size,
            i.lot_size,
            i.is_tradeable,
            i.is_synthetic,
        )
        for i in seed.INSTRUMENTS
    ] == [
        ("ALGOPROFITX_TEST_EQ", "ALGOPROFITX_TEST_EQ", InstrumentType.EQUITY, "INR", Decimal("0.01"), 1, True, True),
        ("NSE:NIFTY_50", "NIFTY 50", InstrumentType.INDEX, "INR", None, None, False, False),
        ("NSE:BANK_NIFTY", "NIFTY BANK", InstrumentType.INDEX, "INR", None, None, False, False),
    ]
    assert {i.exchange_id for i in seed.INSTRUMENTS} == {seed.NSE_EXCHANGE_ID}


# ----------------------------------------------------------------- SQLAlchemy-blocked import proof

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

    MODULES = [
        "app.domain.enums",
        "app.domain.execution_support",
        "app.domain.market_seed",
        "app.persistence.catalyst",
        "app.persistence.catalyst.allocation",
        "app.persistence.catalyst.strategy",
        "app.persistence.catalyst.instrument",
        "app.persistence.catalyst.backtest",
        "app.persistence.catalyst.execution",
        "app.persistence.catalyst.identity",
        "app.persistence.catalyst.auth_session",
    ]
    for name in MODULES:
        importlib.import_module(name)

    loaded = sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)
    orm = sorted(m for m in sys.modules if m.startswith(("app.models", "app.db")))
    print("LOADED=" + repr(loaded))
    print("ORM=" + repr(orm))
    """
)


def test_the_catalyst_persistence_package_imports_with_sqlalchemy_blocked():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "TEST_DATABASE_URL", "PERSISTENCE_PROVIDER", "APP_ENV"}
    }
    environment.update(
        SECRET_KEY="a-long-unique-secret-for-the-sqlalchemy-blocked-probe", PYTHONDONTWRITEBYTECODE="1"
    )
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
    assert lines[-2] == "LOADED=[]"
    assert lines[-1] == "ORM=[]"


# ---------------------------------------------------------------------- ratchet (shrinks per stage)

# Every application module that imports SQLAlchemy directly today. Later stages must remove entries as
# they remove the imports; a stale entry or a new importer fails this test. This list does NOT mean
# SQLAlchemy is gone: the runtime still needs it until the final stage.
SQLALCHEMY_IMPORTERS = frozenset(
    {
        "app/api/routes/allocations.py",
        "app/api/routes/auth.py",
        "app/api/routes/executions.py",
        "app/api/routes/instruments.py",
        "app/api/routes/marketplace.py",
        "app/api/routes/strategies.py",
        "app/bootstrap/instruments.py",
        "app/core/dependencies.py",
        "app/core/health.py",
        "app/db/base.py",
        "app/db/session.py",
        "app/market_data/sql_mapping.py",
        "app/models/allocation.py",
        "app/models/auth_session.py",
        "app/models/backtest.py",
        "app/models/execution.py",
        "app/models/instrument.py",
        "app/models/market_data.py",
        "app/models/strategy.py",
        "app/models/user.py",
        "app/services/allocation.py",
        "app/services/auth.py",
        "app/services/auth_session.py",
        "app/services/backtest.py",
        "app/services/execution.py",
        "app/services/instrument.py",
        "app/services/marketplace.py",
        "app/services/strategy.py",
    }
)


def _imports_sqlalchemy(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "sqlalchemy" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "sqlalchemy":
            return True
    return False


def test_the_set_of_modules_importing_sqlalchemy_only_shrinks():
    found = {
        path.relative_to(BACKEND).as_posix()
        for path in (BACKEND / "app").rglob("*.py")
        if _imports_sqlalchemy(path)
    }
    assert found - SQLALCHEMY_IMPORTERS == set(), "new module imports SQLAlchemy directly"
    assert SQLALCHEMY_IMPORTERS - found == set(), "stale ratchet entry: remove it from SQLALCHEMY_IMPORTERS"


def test_the_domain_and_catalyst_persistence_packages_do_not_import_sqlalchemy():
    offenders = [
        path.relative_to(BACKEND).as_posix()
        for package in ("app/domain", "app/persistence")
        for path in (BACKEND / package).rglob("*.py")
        if _imports_sqlalchemy(path)
    ]
    assert offenders == []
