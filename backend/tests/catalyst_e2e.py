"""An in-memory Catalyst deployment for end-to-end HTTP tests.

The real FastAPI app runs with the Catalyst provider and every repository talks to one
``MemoryDataStore`` whose table uniqueness mirrors the real Development Data Store (recorded from
the console schema view). Nothing here touches a live Catalyst environment.
"""

from __future__ import annotations

import sys

from tests.catalyst_memory import MemoryDataStore, backtest_store, columns_of, strategy_store

# Unique columns of the real Development tables ("Is Unique" in the Data Store schema).
REAL_UNIQUE = {
    "AlgoProfitXUsers": ("user_uuid", "email_lookup"),
    "AlgoProfitXRoles": ("role_name",),
    "AlgoProfitXAuthSessions": ("session_uuid",),
    "AlgoProfitXAuthSessionSlots": ("slot_key", "session_uuid"),
    "AlgoProfitXRefreshClaims": ("claim_hash",),
    "AlgoProfitXExchanges": ("exchange_uuid", "code"),
    "AlgoProfitXInstruments": ("instrument_uuid", "canonical_lookup"),
    "AlgoProfitXStrategies": ("strategy_uuid", "slug_lookup"),
    "AlgoProfitXStrategyVersions": ("version_uuid", "version_key"),
    "AlgoProfitXStrategyLocks": ("strategy_uuid", "owner_token"),
    "AlgoProfitXBacktests": ("backtest_uuid", "request_key"),
    "AlgoProfitXBacktestClaims": ("claim_key", "lease_token"),
    "AlgoProfitXBacktestTerminals": ("backtest_uuid", "terminal_key"),
    "AlgoProfitXAllocations": ("allocation_uuid",),
    "AlgoProfitXExecutions": ("execution_uuid", "idempotency_lookup"),
    "AlgoProfitXExecutionClaims": ("allocation_uuid", "execution_uuid"),
}


def full_store(*, with_schema_column: bool) -> MemoryDataStore:
    """Every application table; strict columns for the two V2-sensitive tables."""
    strategies = strategy_store(with_schema_column=with_schema_column)
    backtests = backtest_store(with_schema_column=with_schema_column)
    schemas = {**strategies.schemas, **backtests.schemas}
    for table in REAL_UNIQUE:
        schemas.setdefault(table, None)
    store = MemoryDataStore(schemas, dict(REAL_UNIQUE))
    # The real Roles table is pre-populated by the operator; registration requires these rows.
    for name in ("ADMIN", "CREATOR", "INVESTOR"):
        store.counter += 1
        store.rows["AlgoProfitXRoles"].append({"ROWID": f"role-{name}", "role_name": name})
    return store


def route_all_catalyst_clients_to(monkeypatch, store: MemoryDataStore) -> None:
    """Make every ``CatalystPersistenceClient(request=...)`` in the app return ``store``."""
    factory = lambda *args, **kwargs: store  # noqa: E731
    for name, module in list(sys.modules.items()):
        if name.startswith("app.") and hasattr(module, "CatalystPersistenceClient"):
            monkeypatch.setattr(module, "CatalystPersistenceClient", factory)
