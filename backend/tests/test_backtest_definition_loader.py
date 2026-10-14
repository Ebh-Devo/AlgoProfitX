"""#50 stage 4: ``load_versioned_definition`` is ORM-free and shared by the SQL and Catalyst paths.

It must behave identically for the SQLAlchemy ``Backtest`` model and the plain ``BacktestRecord``, the
old ``app.services.backtest`` import location must keep working, and ``app.services.backtest_definition``
and ``app.services.catalyst_backtest`` must import with SQLAlchemy blocked. SQLAlchemy is not removed.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.backtesting.contracts import BacktestExecutionError
from app.models.backtest import Backtest
from app.services import backtest as sql_backtest
from app.services import backtest_definition
from tests.test_catalyst_strategy_v2 import V2_ENV, v2_document

BACKEND = Path(__file__).resolve().parents[1]
VERSION_ID = uuid.uuid4()


def _orm(version, configuration, environment):
    return Backtest(
        strategy_version_id=VERSION_ID,
        definition_schema_version=version,
        configuration_snapshot=configuration,
        backtest_configuration_snapshot=environment,
    )


def _plain(version, configuration, environment):
    return SimpleNamespace(
        strategy_version_id=VERSION_ID,
        definition_schema_version=version,
        configuration_snapshot=configuration,
        backtest_configuration_snapshot=environment,
    )


def _outcome(load, backtest):
    try:
        loaded = load(backtest)
    except BacktestExecutionError as exc:
        return ("error", exc.code, str(exc))
    return ("ok", None if loaded is None else loaded.canonical)


CASES = {
    "v1": (1, {}, {}),
    "v2": (2, None, V2_ENV),
    "unsupported_version": (99, {}, {}),
    "invalid_v2_document": (2, {"schema_version": 2}, V2_ENV),
    "invalid_environment": (2, None, {}),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_orm_and_plain_records_load_identically(name):
    version, configuration, environment = CASES[name]
    configuration = v2_document() if configuration is None else configuration
    expected = _outcome(backtest_definition.load_versioned_definition, _plain(version, configuration, environment))
    assert _outcome(backtest_definition.load_versioned_definition, _orm(version, configuration, environment)) == expected
    if name == "v1":
        assert expected == ("ok", None)
    if name == "v2":
        assert expected[0] == "ok" and expected[1] is not None
    if name == "unsupported_version":
        assert expected[:2] == ("error", "strategy_definition_unsupported_version")
    if name == "invalid_v2_document":
        assert expected[:2] == ("error", "strategy_definition_invalid")


def test_the_old_import_location_still_resolves_to_the_same_function():
    assert sql_backtest.load_versioned_definition is backtest_definition.load_versioned_definition


BLOCKED_IMPORT_PROBE = textwrap.dedent(
    """
    import importlib, importlib.abc, sys

    BLOCKED = {"sqlalchemy", "greenlet"}

    class Blocker(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.split(".")[0] in BLOCKED:
                raise ImportError("blocked for the SQLAlchemy-free import probe: " + name)
            return None

    sys.meta_path.insert(0, Blocker())
    for name in ("app.services.backtest_definition", "app.services.catalyst_backtest"):
        importlib.import_module(name)
    print("LOADED=" + repr(sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)))
    print("ORM=" + repr(sorted(m for m in sys.modules if m.startswith(("app.models", "app.db")))))
    """
)


def test_the_definition_loader_and_catalyst_backtest_service_import_with_sqlalchemy_blocked():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "TEST_DATABASE_URL", "PERSISTENCE_PROVIDER", "APP_ENV"}
    }
    environment.update(SECRET_KEY="a-long-unique-secret-for-the-loader-import-probe", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-c", BLOCKED_IMPORT_PROBE],
        cwd=BACKEND, env=environment, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    lines = result.stdout.strip().splitlines()
    assert lines[-2] == "LOADED=[]" and lines[-1] == "ORM=[]"


def test_catalyst_backtest_service_does_not_import_the_sql_backtest_service():
    tree = ast.parse((BACKEND / "app" / "services" / "catalyst_backtest.py").read_text(encoding="utf-8"))
    modules = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
    assert "app.services.backtest" not in modules
