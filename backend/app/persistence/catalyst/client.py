from __future__ import annotations

import asyncio
import re
from threading import Lock
from typing import Any, Callable


class CatalystPersistenceError(RuntimeError):
    """Safe application-level wrapper for Catalyst SDK failures."""


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,127}$")


def _validate_identifier(value: str, label: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"Invalid Catalyst {label}")
    return value


class CatalystPersistenceClient:
    """Lazy, request-scoped access to Catalyst Data Store and ZCQL.

    The SDK is synchronous, so async callers should use the async wrappers.
    The client accepts an initializer only to make the SDK boundary testable;
    production passes the active AppSail request to ``zcatalyst_sdk.initialize``.
    """

    def __init__(
        self,
        initializer: Callable[[], Any] | None = None,
        request: Any | None = None,
    ) -> None:
        self._initializer = initializer
        self._request = request
        self._app: Any | None = None
        self._lock = Lock()

    def initialize(self) -> Any:
        if self._app is not None:
            return self._app

        with self._lock:
            if self._app is not None:
                return self._app
            initializer = self._initializer
            if initializer is None:
                try:
                    import zcatalyst_sdk
                except ImportError as exc:
                    raise CatalystPersistenceError(
                        "Catalyst SDK is not installed"
                    ) from exc
                initializer = lambda: zcatalyst_sdk.initialize(req=self._request)
            try:
                self._app = initializer()
            except Exception as exc:
                raise CatalystPersistenceError(
                    "Catalyst SDK initialization failed"
                ) from exc
            return self._app

    def datastore(self) -> Any:
        try:
            return self.initialize().datastore()
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError(
                "Catalyst Data Store service is unavailable"
            ) from exc

    def zcql(self) -> Any:
        try:
            return self.initialize().zcql()
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError("Catalyst ZCQL service is unavailable") from exc

    def table(self, table_name: str) -> Any:
        _validate_identifier(table_name, "table name")
        try:
            return self.datastore().table(table_name)
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError(
                "Catalyst Data Store table is unavailable"
            ) from exc

    def insert_row(self, table_name: str, row_data: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self.table(table_name).insert_row(row_data)
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError("Catalyst row insert failed") from exc
        if not isinstance(result, dict):
            raise CatalystPersistenceError("Catalyst insert returned an invalid row")
        return result

    def update_row(self, table_name: str, row_data: dict[str, Any]) -> dict[str, Any]:
        if not row_data.get("ROWID"):
            raise ValueError("Catalyst update requires ROWID")
        try:
            result = self.table(table_name).update_row(row_data)
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError("Catalyst row update failed") from exc
        if not isinstance(result, dict):
            raise CatalystPersistenceError("Catalyst update returned an invalid row")
        return result

    def delete_row(self, table_name: str, row_id: str) -> Any:
        if not row_id:
            raise ValueError("Catalyst delete requires ROWID")
        try:
            return self.table(table_name).delete_row(row_id)
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError("Catalyst row delete failed") from exc

    def execute_query(self, query: str) -> Any:
        if not query or not query.strip():
            raise ValueError("Catalyst query must not be blank")
        try:
            return self.zcql().execute_query(query)
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError("Catalyst ZCQL query failed") from exc

    def submit_job(self, job_meta: dict[str, Any]) -> dict[str, Any]:
        """Submit one Catalyst Job Scheduling job with admin scope."""
        try:
            result = self.initialize().job_scheduling().job.submit_job(dict(job_meta))
        except CatalystPersistenceError:
            raise
        except Exception as exc:
            raise CatalystPersistenceError("Catalyst job submission failed") from exc
        if (
            not isinstance(result, dict)
            or result.get("status") is not True
            or not result.get("job_id")
        ):
            raise CatalystPersistenceError("Catalyst job submission returned invalid data")
        return result

    def query_rows(self, query: str, table_name: str) -> list[dict[str, Any]]:
        """Return rows from the table-keyed structure produced by ZCQL."""
        validated_table = _validate_identifier(table_name, "table name")
        result = self.execute_query(query)
        if not isinstance(result, list):
            raise CatalystPersistenceError("Catalyst ZCQL returned invalid rows")

        rows: list[dict[str, Any]] = []
        for item in result:
            if not isinstance(item, dict):
                raise CatalystPersistenceError("Catalyst ZCQL returned invalid rows")
            row = item.get(validated_table)
            if not isinstance(row, dict):
                raise CatalystPersistenceError("Catalyst ZCQL returned invalid rows")
            rows.append(row)
        return rows

    def readiness(self, probe_table: str) -> bool:
        table_name = _validate_identifier(probe_table, "probe table name")
        self.execute_query(f"SELECT ROWID FROM {table_name} LIMIT 1")
        return True

    def connectivity_checks(self, probe_table: str) -> dict[str, bool]:
        """Return safe stage results without serializing SDK exceptions."""
        table_name = _validate_identifier(probe_table, "probe table name")
        checks = {
            "sdk_initialization": False,
            "datastore_access": False,
            "zcql_access": False,
        }
        try:
            self.initialize()
        except CatalystPersistenceError:
            return checks
        checks["sdk_initialization"] = True

        try:
            self.datastore()
        except CatalystPersistenceError:
            pass
        else:
            checks["datastore_access"] = True

        try:
            self.execute_query(f"SELECT ROWID FROM {table_name} LIMIT 1")
        except CatalystPersistenceError:
            pass
        else:
            checks["zcql_access"] = True
        return checks

    async def async_readiness(self, probe_table: str) -> bool:
        return await asyncio.to_thread(self.readiness, probe_table)

    async def async_connectivity_checks(self, probe_table: str) -> dict[str, bool]:
        return await asyncio.to_thread(self.connectivity_checks, probe_table)

    async def async_insert_row(
        self,
        table_name: str,
        row_data: dict[str, Any],
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self.insert_row, table_name, row_data)

    async def async_update_row(
        self,
        table_name: str,
        row_data: dict[str, Any],
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self.update_row, table_name, row_data)

    async def async_delete_row(self, table_name: str, row_id: str) -> Any:
        return await asyncio.to_thread(self.delete_row, table_name, row_id)

    async def async_query_rows(
        self,
        query: str,
        table_name: str,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.query_rows, query, table_name)

    async def async_submit_job(self, job_meta: dict[str, Any]) -> dict[str, Any]:
        return await asyncio.to_thread(self.submit_job, job_meta)
