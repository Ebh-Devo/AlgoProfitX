"""app.domain.enums is ORM-free and keeps every legacy import path and persisted value intact."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

# enum name -> (legacy module, {member: value}); values are persisted, so they are frozen here.
SNAPSHOT = {
    "StrategyStatus": ("app.models.strategy", {"DRAFT": "draft", "PUBLISHED": "published", "DEPLOYED": "deployed", "ARCHIVED": "archived"}),
    "InstrumentType": ("app.models.instrument", {"EQUITY": "equity", "INDEX": "index"}),
    "BacktestStatus": ("app.models.backtest", {"QUEUED": "queued", "RUNNING": "running", "COMPLETED": "completed", "FAILED": "failed"}),
    "AllocationStatus": ("app.models.allocation", {"ACTIVE": "active"}),
    "ExecutionStatus": ("app.models.execution", {"PENDING": "pending", "RUNNING": "running", "COMPLETED": "completed", "FAILED": "failed"}),
    "MarketDataDatasetStatus": ("app.models.market_data", {"READY": "ready", "FAILED": "failed"}),
}

# enum name -> PostgreSQL type name bound by the model column (unchanged by the move).
PG_TYPE_NAMES = {
    "StrategyStatus": "strategy_status",
    "InstrumentType": "instrument_type",
    "BacktestStatus": "backtest_status",
    "AllocationStatus": "allocation_status",
    "ExecutionStatus": "execution_status",
    "MarketDataDatasetStatus": "market_data_dataset_status",
}


def test_importing_domain_enums_does_not_load_sqlalchemy():
    clean = {
        key: value
        for key, value in os.environ.items()
        if key not in {"DATABASE_URL", "TEST_DATABASE_URL", "PERSISTENCE_PROVIDER", "APP_ENV"}
    }
    clean.update(SECRET_KEY="a-long-unique-secret-for-the-isolated-enum-probe", PYTHONDONTWRITEBYTECODE="1")
    probe = "import sys, app.domain.enums; print(sorted(m for m in sys.modules if m.split('.')[0] == 'sqlalchemy'))"
    result = subprocess.run([sys.executable, "-c", probe], cwd=BACKEND, env=clean, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip().splitlines()[-1] == "[]"


@pytest.mark.parametrize("name", sorted(SNAPSHOT))
def test_enum_members_and_values_are_frozen(name):
    from app.domain import enums

    _, members = SNAPSHOT[name]
    enum_class = getattr(enums, name)
    assert issubclass(enum_class, str)
    assert {member.name: member.value for member in enum_class} == members


@pytest.mark.parametrize("name", sorted(SNAPSHOT))
def test_legacy_import_paths_yield_the_identical_class(name):
    from app import models
    from app.domain import enums

    module_name, _ = SNAPSHOT[name]
    canonical = getattr(enums, name)
    assert getattr(importlib.import_module(module_name), name) is canonical
    assert getattr(models, name) is canonical


@pytest.mark.parametrize("name", sorted(SNAPSHOT))
def test_database_enum_type_name_and_values_are_unchanged(name):
    from app import models  # noqa: F401  (registers every table on the metadata)
    from app.db.base import Base
    from app.domain import enums

    _, members = SNAPSHOT[name]
    columns = [
        column
        for table in Base.metadata.tables.values()
        for column in table.columns
        if getattr(column.type, "enum_class", None) is getattr(enums, name)
    ]
    assert len(columns) == 1
    assert columns[0].type.name == PG_TYPE_NAMES[name]
    assert list(columns[0].type.enums) == list(members.values())
