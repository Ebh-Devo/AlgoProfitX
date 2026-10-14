"""#50 stage 5: ``resolve_mapping`` lives in the SQL-only ``app.market_data.sql_mapping``.

The plain parts of ``app.market_data`` must import with SQLAlchemy blocked, the old import location must
keep resolving to the same function, and the SQL module must be the only one importing SQLAlchemy.
SQLAlchemy is not removed from the runtime by this stage.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]


def test_the_old_import_location_resolves_to_the_same_function():
    from app.market_data import infrastructure, sql_mapping
    from app.market_data.infrastructure import resolve_mapping
    from app.services import backtest

    assert resolve_mapping is sql_mapping.resolve_mapping
    assert backtest.resolve_mapping is sql_mapping.resolve_mapping
    assert infrastructure.resolve_mapping is sql_mapping.resolve_mapping


def test_unknown_infrastructure_attributes_still_raise_attribute_error():
    from app.market_data import infrastructure

    with pytest.raises(AttributeError):
        infrastructure.does_not_exist  # noqa: B018


def _imports_sqlalchemy(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "sqlalchemy" for a in node.names):
            return True
        if isinstance(node, ast.ImportFrom) and node.level == 0 and (node.module or "").split(".")[0] == "sqlalchemy":
            return True
    return False


def test_only_the_sql_mapping_module_imports_sqlalchemy_or_the_orm_in_market_data():
    package = BACKEND / "app" / "market_data"
    assert sorted(p.name for p in package.glob("*.py") if _imports_sqlalchemy(p)) == ["sql_mapping.py"]
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        orm = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app.models")]
        assert bool(orm) == (path.name == "sql_mapping.py"), path.name


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
    import app.market_data
    from app.market_data.infrastructure import MarketDataError, ProviderRegistry, canonical_checksum, dataset_key
    assert MarketDataError("market_data_timeout", "x").code == "market_data_timeout"
    try:
        from app.market_data.infrastructure import resolve_mapping
    except ImportError as exc:
        print("SQL=blocked")
    else:
        raise SystemExit("resolve_mapping must need SQLAlchemy")
    print("LOADED=" + repr(sorted(m for m in sys.modules if m.split(".")[0] in BLOCKED)))
    print("ORM=" + repr(sorted(m for m in sys.modules if m.startswith(("app.models", "app.db")))))
    """
)


def test_the_plain_market_data_modules_import_with_sqlalchemy_blocked():
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "TEST_DATABASE_URL", "PERSISTENCE_PROVIDER", "APP_ENV"}
    }
    environment.update(SECRET_KEY="a-long-unique-secret-for-the-market-data-import-probe", PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-c", BLOCKED_IMPORT_PROBE],
        cwd=BACKEND, env=environment, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-3000:] + result.stdout[-1000:]
    lines = result.stdout.strip().splitlines()
    assert lines[-3] == "SQL=blocked" and lines[-2] == "LOADED=[]" and lines[-1] == "ORM=[]"
