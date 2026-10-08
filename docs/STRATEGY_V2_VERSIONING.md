# Strategy V2 — Phase 6: version boundary and service wiring

Wires the Phase 1–5 Strategy Definition V2 architecture into the strategy/backtest service
boundary. Implements §23 Phase 6 of [STRATEGY_DEFINITION_V2.md](STRATEGY_DEFINITION_V2.md). V1 behaviour
is unchanged; the runtime is [Phase 5](STRATEGY_RUNTIME_PHASE5.md).

## The version boundary

`strategy_versions.definition_schema_version` (integer, `NOT NULL`, server default `1`) is the
**only** selector of how `configuration` is interpreted. The JSON is never sniffed to decide it.

| persisted value | meaning | path |
|---|---|---|
| `1` | V1 | V1 compatibility adapter; backtests run on the unchanged `EmaCrossoverReferenceEngine` |
| `2` | V2 | V2 loader → semantic/capability validation → Phase 5 `StrategyRuntimeEngine` |
| anything else (`0`, `3`, `"2"`, `true`, …) | — | `UnsupportedSchemaVersionError` — no fallback |

`backtests.definition_schema_version` snapshots the version alongside `configuration_snapshot`
(same migration), so a backtest is interpreted exactly as it was requested even though execution
reads only its own snapshots.

### Legacy records

Existing rows are V1 by construction: the migration adds the column with constant server default `1`,
so Postgres backfills every historical row to `1` with no row rewrite, and **no strategy JSON is
touched**. A record that has no value at all (an object that never went through the database) is
resolved to `1` by `resolve_schema_version(None)`. This is the one documented compatibility rule,
and it is the same rule at both levels.

The downgrade drops the column but refuses to run while any non-V1 row exists, so a V2 row can
never be silently re-read as V1.

## The loader — `app/strategy_definition/versioning.py`

`load_strategy_definition(strategy_version)` (and `load_definition_for_version(version, configuration,
backtest_configuration)`, which the backtest service calls with its snapshots) is the authoritative
boundary. No service interprets V1 or V2 JSON itself. Order, for either version:

```
resolve persisted version → JSON/schema load → semantic + position validation → capability check
```

| failure | raised |
|---|---|
| version not 1/2 | `UnsupportedSchemaVersionError` (a `StrategyDefinitionError`) |
| malformed for its version (including a V1 document stored as 2) | `StrategyDefinitionError` |
| semantically invalid; capability the runtime lacks | `RuntimeSetupError` (`.issues`; capability issues have code `capability_missing`) |

`detect_schema_version` / `load_definition` in `loading.py` are the Phase 1–5 shape-based helpers.
They remain only for the offline engine entry points and the parity tests; **services must not use them**.

## Backtest routing — `app/services/backtest.py`

`execute_backtest` resolves the snapshotted version **before** market data is requested:

```
claim → load persisted version → (V2: load, schema, semantic, capability, environment) → market data → run
```

* **V1** → `EmaCrossoverReferenceEngine`, byte-for-byte the previous behaviour.
* **V2** → `StrategyRuntimeEngine.run_canonical(canonical, backtest_configuration, candles)`. It reuses
  the Phase 5 runtime (rules → conflicts → planner → `OrderIntent` → adapter → events → ledger); there is
  no second V2 execution implementation. The result is the existing `BacktestExecutionResult`, stored in the
  existing `result_summary` shape (V2 trades add `signal_timestamp`, `fill_timestamp`, `exit_reason`, … —
  additive).

A doomed V2 backtest ends `failed` with a stable `error_code`, before any dataset is acquired and before any
candle is processed:

| `error_code` | cause |
|---|---|
| `strategy_definition_unsupported_version` | persisted version not 1/2 (also fails a V1-looking row) |
| `strategy_definition_invalid` | schema or semantic validation failed |
| `strategy_definition_unsupported_capability` | the definition needs something Phase 5 does not provide |
| `strategy_environment_invalid` | `backtest_configuration` unusable (e.g. a V2 run with no `fill_model`) |

## Creation

* Public `POST /strategies/{id}/versions` is unchanged: it always persists `1`. A configuration carrying a V2
  envelope (`schema` / `schema_version`) is **refused (422)** rather than stored as V1, where its fields
  would be silently ignored. The response shape is unchanged (it does not expose the version).
* V2 has **no public API yet** (non-goal). The internal entry point is
  `services.strategy.create_strategy_version_v2(session, strategy, *, instrument_id, configuration,
  backtest_configuration)`, which validates schema + semantics (not runtime capabilities — a valid
  definition needing a future capability may be stored) and persists version `2`.

## Tests

* `tests/test_strategy_definition_versioning.py` — resolution, authority of the persisted version, layers.
* `tests/test_strategy_v2_service_wiring.py` — persistence round-trip, legacy row, V1/V2 routing, failure
  ordering (market data and runtime are monkeypatched to fail if reached).
* The Phase 5 parity fixtures (`strategy_v2_parity.json`, `strategy_v2_runtime_parity.json`) are unmodified.

## Known limitations

* No DB `CHECK` on the column: unsupported values are rejected by the loader (deterministically), not by
  Postgres, so a future version can be introduced without a constraint migration.
* The V2 backtest uses the same synthetic provider and 1d timeframe as V1; no new providers.
* The persisted version is not exposed in API responses (deliberate: no response redesign).
