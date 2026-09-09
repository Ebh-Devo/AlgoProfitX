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
    zcql.execute_query.return_value = [{"MigrationProbe": {"ROWID": "probe-1"}}]
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
    assert selected == [{"MigrationProbe": {"ROWID": "probe-1"}}]
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


def test_query_rows_unwraps_the_documented_table_key(catalyst_services):
    app, _, zcql = catalyst_services
    client = CatalystPersistenceClient(Mock(return_value=app))

    rows = client.query_rows(
        "SELECT ROWID FROM MigrationProbe LIMIT 1",
        "MigrationProbe",
    )

    assert rows == [{"ROWID": "probe-1"}]
    zcql.execute_query.assert_called_once_with(
        "SELECT ROWID FROM MigrationProbe LIMIT 1"
    )


def test_query_rows_rejects_unexpected_zcql_shapes(catalyst_services):
    app, _, zcql = catalyst_services
    zcql.execute_query.return_value = [{"ROWID": "probe-1"}]
    client = CatalystPersistenceClient(Mock(return_value=app))

    with pytest.raises(CatalystPersistenceError, match="invalid rows"):
        client.query_rows(
            "SELECT ROWID FROM MigrationProbe LIMIT 1",
            "MigrationProbe",
        )


def test_connectivity_checks_report_each_safe_stage(catalyst_services):
    app, _, zcql = catalyst_services
    client = CatalystPersistenceClient(Mock(return_value=app))

    assert client.connectivity_checks("MigrationProbe") == {
        "sdk_initialization": True,
        "datastore_access": True,
        "zcql_access": True,
    }
    zcql.execute_query.assert_called_once_with(
        "SELECT ROWID FROM MigrationProbe LIMIT 1"
    )


def test_connectivity_checks_fail_closed_without_exposing_sdk_errors():
    client = CatalystPersistenceClient(Mock(side_effect=RuntimeError("secret")))

    assert client.connectivity_checks("MigrationProbe") == {
        "sdk_initialization": False,
        "datastore_access": False,
        "zcql_access": False,
    }


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


def test_default_initializer_passes_the_request_to_the_sdk(monkeypatch):
    request = object()
    initialized_app = Mock()
    initialize = Mock(return_value=initialized_app)
    sdk = Mock(initialize=initialize)
    monkeypatch.setitem(__import__("sys").modules, "zcatalyst_sdk", sdk)

    client = CatalystPersistenceClient(request=request)

    assert client.initialize() is initialized_app
    initialize.assert_called_once_with(req=request)
