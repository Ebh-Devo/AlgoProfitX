# Strategy V2 — Phase 7B-2: creator frontend

Frontend half of the plan in [STRATEGY_V2_PHASE7A_API_CONTRACT_AUDIT.md](STRATEGY_V2_PHASE7A_API_CONTRACT_AUDIT.md), on top of the backend contract in [STRATEGY_V2_PHASE7B1_API_CONTRACT.md](STRATEGY_V2_PHASE7B1_API_CONTRACT.md).
No backend, runtime, indicator or migration change; `src/api/generated/openapi.ts` was already current (regenerating from the merged app produces no diff).

## User flow

1. **Create the strategy** as before (`/creator/strategies/new`) — identity is unchanged.
2. On the strategy page choose **Create Version**, then pick the **definition version** (radio group: Strategy V1 / Strategy V2). V1 stays the default so the existing flow is untouched. The choice is explicit; nothing is inferred from JSON. Both creators stay mounted once opened, so switching never discards a draft.
3. **V2 builder** (`features/creator/v2/V2Builder.tsx`): instrument → position (direction, explicit share count) → rules (condition tree + action) → backtest settings → validate / save.
4. **Validate** calls `POST /strategies/definitions/validate` and writes nothing. The verdict (`valid` / `savable` / `runnable`, issues grouped by section, unsupported capabilities) is shown verbatim.
5. **Save Version** is enabled only when the verdict for the *current, unchanged* request says `runnable` (any edit invalidates it). It calls `POST /strategies/{id}/versions/v2` with `definition_schema_version: 2`, then navigates to the new Version, where the existing Backtests panel runs it.

## Where capability comes from

Every list of choices (timeframes, evaluation modes, fill models, leg sides, operations, condition kinds, operators, directions, operand kinds, price fields, indicators and their parameters/outputs) is read from `GET /strategies/definition-vocabulary`. `v2/definition.ts` holds only presentation labels and the form-to-document translation. If the vocabulary fails to load the builder shows a retryable error and **no controls**: there is no hardcoded fallback. The builder additionally limits operations to `open`/`close` (the only ones it can author without an amount) and conditions to the six kinds it can render, even if the vocabulary advertises more.

## Structured errors

`ApiError` (`api/client.ts`) now keeps an object-shaped `detail` (`{code, message, issues}`) as `error.code` / `error.issues` instead of discarding it, so:

* V2 create `422`s (`invalid_strategy_definition`, `strategy_definition_not_runnable`) render the backend's issues; `409` (version race) says nothing was saved and to retry.
* The lifecycle guard `409` (`strategy_definition_version_unsupported_for_execution`) now shows its real message.
* String and FastAPI list details behave exactly as before (V1 unaffected).

## Version-aware views

* Version list/detail, backtest configure and run pages show **Strategy V1/V2 from the persisted `definition_schema_version`** (`BacktestResponse` carries its own).
* `AlgorithmSummary` / `StartingCapitalSummary` take `schemaVersion`; V2 renders rules as sentences ("When EMA(9) crosses above EMA(21), open a long position."), V1 renders as before. A document that does not match the V2 grammar is summarised as "could not be summarised", never guessed. Raw JSON stays only in the collapsed "Advanced / Technical details".
* **Lifecycle:** *Publish* is disabled when the latest Version is V2 and *Deploy* when the current Version is V2 (mirroring the backend, which checks those versions), with a notice that V2 is backtest-only because the execution adapter does not support it. The backend remains the authority.
* Backtest honesty: the "Completed synthetic run" heading is now conditional on `market_data_provenance.synthetic`; failed runs show the backend `error_code` plus a recovery hint for the 7B-1 codes (`strategy_definition_invalid`, `…_unsupported_capability`, `strategy_environment_invalid`, `strategy_runtime_failed`). Runtime errors are never labelled market-data errors by the UI.

## Backtest configuration

The V2 environment sent to both endpoints is `{initial_capital, timeframe, fill_model}`. No date range is sent: the backend does not require one and V1 sends none. Capital is labelled a simulation parameter, not a deposit.

## Known limitations

* Rules are checked by the backend only; client-side checks are limited to values that cannot be serialised (blank/non-numeric fields) and a missing instrument.
* The builder authors one core position with one leg and `open`/`close` operations, matching the current vocabulary. It is a form, not a free-form graph editor; nested conditions are limited to 3 levels.
* In-app route changes are not intercepted (the app uses `createBrowserRouter` but tests use `MemoryRouter`); a draft is protected by a discard confirmation on Cancel and a `beforeunload` prompt.
* V2 versions cannot be edited or published; creating a new Version is the only way to change a definition.
* Backtests use whatever market-data provider the server is configured with; with the reference provider results are synthetic and labelled so.
