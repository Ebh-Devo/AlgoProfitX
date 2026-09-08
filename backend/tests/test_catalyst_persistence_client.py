from unittest.mock import Mock

import pytest

from app.persistence.catalyst.client import (
    CatalystPersistenceClient,
    CatalystPersistenceError,
)


@pytest.fixture
def catalyst_services():
    table = Mock()
    table.insert_row.return_value = {"ROWID": "probe-1", "value": "before"}
    table.update_row.return_value = {"ROWID": "probe-1", "value": "after"}
    datastore = Mock()
    datastore.table.return_value = table
    zcql = Mock()
    zcql.execute_query.return_value = [{"ROWID": "probe-1"}]
    app = Mock(datastore=Mock(return_value=datastore), zcql=Mock(return_value=zcql))
    return app, table, zcql


def test_initializes_once_and_exposes_documented_crud(catalyst_services):
    app, table, zcql = catalyst_services
    initializer = Mock(return_value=app)
    client = CatalystPersistenceClient(initializer)

    inserted = client.insert_row("MigrationProbe", {"value": "before"})
    selected = client.execute_query("SELECT ROWID FROM MigrationProbe LIMIT 1")
    updated = client.update_row(
        "MigrationProbe", {"ROWID": inserted["ROWID"], "value": "after"}
    )
    client.delete_row("MigrationProbe", inserted["ROWID"])

    assert inserted["ROWID"] == "probe-1"
    assert selected == [{"ROWID": "probe-1"}]
    assert updated["value"] == "after"
    initializer.assert_called_once_with()
    table.insert_row.assert_called_once_with({"value": "before"})
    table.update_row.assert_called_once_with(
        {"ROWID": "probe-1", "value": "after"}
    )
    table.delete_row.assert_called_once_with("probe-1")
    zcql.execute_query.assert_called_once_with(
        "SELECT ROWID FROM MigrationProbe LIMIT 1"
    )


def test_readiness_uses_a_validated_probe_table(catalyst_services):
    app, _, zcql = catalyst_services
    client = CatalystPersistenceClient(Mock(return_value=app))

    assert client.readiness("MigrationProbe") is True
    zcql.execute_query.assert_called_once_with(
        "SELECT ROWID FROM MigrationProbe LIMIT 1"
    )


@pytest.mark.parametrize("table_name", ["Migration Probe", "probe;DROP", "1probe"])
def test_rejects_untrusted_table_names(catalyst_services, table_name):
    app, _, _ = catalyst_services
    client = CatalystPersistenceClient(Mock(return_value=app))

    with pytest.raises(ValueError, match="table name"):
        client.table(table_name)


def test_wraps_sdk_initialization_errors():
    client = CatalystPersistenceClient(Mock(side_effect=RuntimeError("secret")))

    with pytest.raises(CatalystPersistenceError, match="initialization failed") as error:
        client.initialize()

    assert "secret" not in str(error.value)