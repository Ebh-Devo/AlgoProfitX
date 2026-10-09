# Strategy V2 — Phase 7B-1: backend API contract

Implements the backend half of the plan in [STRATEGY_V2_PHASE7A_API_CONTRACT_AUDIT.md](STRATEGY_V2_PHASE7A_API_CONTRACT_AUDIT.md).
No new engine capability, indicator, migration or frontend change.

## Endpoints (all under `/api/v1/strategies`, creator role)

| Method / path | Purpose |
|---|---|
| `POST /definitions/validate` | Stateless V2 draft check. Body `{definition_schema_version: 2, configuration, backtest_configuration}` (`extra="forbid"`). Always `200` for a well-formed body; `422` only for a malformed one. Rate-limited (`DEFINITION_VALIDATION_*` settings). Writes nothing. |
| `POST /{strategy_id}/versions/v2` | Create a V2 version. Body adds `instrument_id`; `definition_schema_version: Literal[2]` is required, unknown fields are rejected. Saves only **runnable** definitions, stored verbatim as version 2. |
| `GET /definition-vocabulary` | The runnable V2 subset, derived from `RUNTIME_CAPABILITIES` + `DEFAULT_CATALOG` (no second registry). |
| `POST /{strategy_id}/versions` (V1) | Gains optional `definition_schema_version: Literal[1] \| None`; a body claiming anything else is `422`. |

`StrategyVersionResponse` and `BacktestResponse` now carry `definition_schema_version` (from the persisted column / the backtest snapshot; never inferred from JSON).

## Verdicts (`strategy_definition/assessment.py`)

Layers run in order: `schema` → `semantic` → `position` → `capability` → `environment`.

* `savable` — no error in schema/semantic/position (a well-formed definition).
* `runnable` — `savable` **and** every required capability is provided **and** the environment passes.
* `valid` — no error-severity issue in any layer. Warnings never fail anything and are always returned.

Each issue is `{path, code, message, severity, layer}`; `required_capabilities` / `unsupported_capabilities` are returned alongside.

`POST …/versions/v2` returns `422` with `detail = {code, message, issues}`: `invalid_strategy_definition` (not savable) or `strategy_definition_not_runnable` (savable, but the runtime cannot execute it). Missing/unknown strategy → `404`, bad instrument → `422` (string, as V1), version-number race → `409`.

## Pre-run hardening (H1–H4)

All fail before market data is requested.

* **H1** — only `same_bar_close` is accepted (`fill_model_unsupported` / `fill_model_required`).
* **H2** — `rules[].limits` is now the capability `rule.limits`, which the runtime does not provide → `strategy_definition_unsupported_capability`.
* **H3** — V2 requires `backtest_configuration.timeframe`, equal to the definition timeframe, and the timeframe must be `1d` (`timeframe_required`, `timeframe_mismatch`, `timeframe_unsupported`). Environment failures map to `strategy_environment_invalid`.
* **H4** — runtime failures are classified by `runtime_error_code`: only `RuntimeDataError` stays `market_data_invalid_payload`; setup/unsupported-operation/execution/unexpected failures are `strategy_definition_invalid`, `strategy_definition_unsupported_capability` or `strategy_runtime_failed`. V1 error handling is unchanged.

## Lifecycle guard (H5)

`publish_strategy`, `deploy_strategy` and `create_allocation` call `require_execution_supported`, so V2 (any non-V1 version) cannot be published, deployed or allocated, whichever caller reaches the service. Routes return `409` with `detail = {code: "strategy_definition_version_unsupported_for_execution", message}`. V1 is untouched.

## Known limitations

* The structured `409` detail (and the structured `422` detail) are objects; the current frontend `normalizeDetail` renders object details generically until the 7B-2 client change.
* `eq` is accepted by the validator only between two constants (a comparison that never changes); against any price/indicator series it is rejected. The vocabulary therefore advertises only `gt`, `gte`, `lt`, `lte`, and regression tests assert advertised operators validate and non-advertised ones do not.
* `create_strategy_version_v2` (service) stays permissive by design; only the route requires `runnable`.
