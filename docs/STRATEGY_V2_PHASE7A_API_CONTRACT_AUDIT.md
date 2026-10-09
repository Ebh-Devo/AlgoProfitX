# Strategy V2 — Phase 7A: frontend authoring API contract audit

Read-only audit of `dev` at `3e1c25b` (after Phase 6, PR #38). It establishes the API contract the Phase 7B
V2 authoring UI may rely on. **No code, schema, migration or behaviour was changed by this audit.**

Labels used throughout:

* **[V]** verified fact: read in the code or reproduced by running the code (file references given).
* **[R]** recommendation: a proposal, not existing behaviour.
* **[Q]** open question: needs a product/engineering decision.

Probe results marked *(probe)* come from calling `load_definition_for_version(...)` and
`StrategyRuntimeEngine.run_canonical(...)` directly on a small hand-built definition over 120 locally generated
candles. They were run from a scratch script outside the repository; nothing was persisted.

Related: [STRATEGY_DEFINITION_V2.md](STRATEGY_DEFINITION_V2.md) (spec),
[STRATEGY_RUNTIME_PHASE5.md](STRATEGY_RUNTIME_PHASE5.md), [STRATEGY_V2_VERSIONING.md](STRATEGY_V2_VERSIONING.md).

---

## 1. Summary

1. **[V]** V2 versions can only be created by an internal service function that no route calls. There is no public
   way to create, validate-before-save, or list the V2 vocabulary.
2. **[V]** The backend *accepts for storage* more than the runtime *can run*. Several documents pass the save gate and
   then fail at execution (e.g. `sma@1`, `rsi@1`, `risk`, multi-leg, `intraday` timeframes). Two further cases pass
   **both** gates and only fail mid-run, with a misleading error code (`limits`, any unsupported `fill_model`).
   A third, a non-`1d` daily/weekly timeframe such as `1w`, **runs silently on daily candles** (see G6).
3. **[V]** Neither `StrategyVersionResponse` nor `BacktestResponse` exposes `definition_schema_version`, and the public V1
   request model ignores unknown fields, so a client sending `definition_schema_version: 2` to the V1 route would be
   stored as V1 without complaint (G3). The UI must not be built on that route.
4. **[V]** Publish/deploy/allocation do not look at the version type; a published V2 version would fail only later, at
   paper execution (G8).
5. **[R]** Phase 7B should start with a small backend contract PR (validate + create-V2 endpoints, version exposure,
   structured errors, two hardening fixes) *before* any UI. §9 lays out the split.

---

## 2. Current V1 flow, end to end

### 2.1 Creation

| Step | Where | Facts |
|---|---|---|
| Create strategy | `StrategyNewPage` → `strategiesApi.create` → `POST /strategies` (`api/routes/strategies.py:60`) | **[V]** body `{name, slug?, description?}`; creator role required (`require_creator`); server derives a unique slug when omitted (`services/strategy.py:60`). |
| Create version | `VersionCreator` (`frontend/src/features/creator/StrategyPages.tsx:608`) → `POST /strategies/{id}/versions` | **[V]** body `StrategyVersionCreateRequest {instrument_id, configuration, backtest_configuration}` (`schemas/strategy.py:59`). |
| V1 config shape | `strategyConfig.ts` `buildConfiguration` | **[V]** `{entry:{type:"ema_crossover",action,direction,fast_period,slow_period}, exit?:{…}}`; `backtest_configuration = {initial_capital}` only. |
| Validation | pydantic `_validate_rules` → `validate_rule_configuration` (`strategy_rules.py`); service `_create_version` | **[V]** errors become 422 (`StrategyVersionValidationError`) with `detail` = a **string**, or 409 for a version-number race. Instrument must exist and be active. |
| Persist | `create_strategy_version` → `_create_version` | **[V]** always `definition_schema_version = 1`. A configuration containing `schema` or `schema_version` is refused with 422 (`services/strategy.py:214`, test `test_the_public_v1_endpoint_refuses_a_v2_envelope…`). |
| Versions are immutable | no update/delete route exists | **[V]** |

### 2.2 Backtest

| Step | Where | Facts |
|---|---|---|
| Configure | `VersionBacktests` (`BacktestPages.tsx:64`) | **[V]** shows version-fixed settings; only an optional `market_data_reference` (≤500 chars) is user input. |
| Create | `POST …/versions/{vid}/backtests` | **[V]** body `{market_data_reference?}`; rate-limited (`backtest_burst_*`, `backtest_sustained_*`); service snapshots `configuration`, `backtest_configuration` and (Phase 6) `definition_schema_version` onto the `Backtest` row, status `queued`. |
| Execute | `POST …/backtests/{bid}/execute` | **[V]** claims `queued`→`running`, resolves the *snapshotted* version, loads/validates V2 *before* market data, acquires dataset, runs V1 reference engine or `StrategyRuntimeEngine`, stores `result_summary`, ends `completed`/`failed` (`services/backtest.py:130`). 503 when `backtest_execution_mode == "disabled"`; per-user concurrency slot. Execution is **synchronous inline**: the HTTP call returns the finished row. |
| Inspect | `GET …/backtests`, `GET …/{bid}`, `GET …/{bid}/analytics` | **[V]** `BacktestResponse` carries `status`, snapshots, dataset/provenance, `result_summary`, `error_message`, `error_code`. Analytics only for `completed`; 409 otherwise. The frontend runs create→execute back-to-back (`navigate(..., {state:{autoRun:true}})`). |

### 2.3 Frontend error handling **[V]**

`api/client.ts` `ApiError(status, message, fieldErrors, requestId)`. `normalizeDetail`:
string → message; array (pydantic) → `fieldErrors[{path,message}]`; **anything else (e.g. an object) → the generic
"The request could not be completed."** 5xx → message with request id. Pages render `errorMessage(error, fallback)` into
`Alert`/`ErrorPanel`/`field-error`. A structured V2 `issues` payload therefore needs a client change (§7.3).

---

## 3. Phase 6 V2 entry points and public-exposure gaps

### 3.1 Entry points **[V]**

| Function | Location | Role |
|---|---|---|
| `create_strategy_version_v2(session, strategy, *, instrument_id, configuration, backtest_configuration)` | `services/strategy.py:228` | Validates via `load_definition_for_version(2, …, check_runtime_capabilities=False)` (schema + semantic + position; **not** capabilities), then `_create_version(…, 2)`. Raises `StrategyVersionValidationError("Invalid V2 definition: <joined string>")`. **Called only from tests** (`tests/test_strategy_v2_service_wiring.py`); no route, no other caller. |
| `load_definition_for_version` / `load_strategy_definition` | `strategy_definition/versioning.py` | The authoritative loader. `resolve_schema_version` accepts exactly int `1` or `2`; `None` → 1; everything else raises `UnsupportedSchemaVersionError`. The JSON is never sniffed. |
| `_load_versioned_definition` | `services/backtest.py:208` | Execution-time gate; maps failures to `error_code`. |

### 3.2 Can a public endpoint safely expose `create_strategy_version_v2`? **[V]/[R]**

**Yes, with the hardening below.** The function does no ownership or commit handling; the route would supply
ownership (`get_strategy(strategy_id, creator_id)`), commit and error mapping exactly as `create_version` does.
It cannot silently produce a V1 row: it hard-codes `V2_SCHEMA_VERSION`, and the loader rejects a document whose own
`schema_version` is not 2 (`loader._load`, enforcing the spec's "column and JSON must agree"). Conditions before exposing it: G1–G7 below.

### 3.3 Gaps (each is verified)

| # | Gap | Evidence | Consequence |
|---|---|---|---|
| **G1** | No public V2 create route. | `create_strategy_version_v2` has no route caller. | UI cannot save V2. |
| **G2** | No validate-without-saving route. | No route imports the loader. | UI cannot give pre-save feedback; save-then-fail would create immutable junk versions (versions are undeletable). |
| **G3** | `definition_schema_version` is absent from `StrategyVersionResponse` and `BacktestResponse`; the frontend never references it. Public V1 request models have no `extra="forbid"`, so a stray `definition_schema_version: 2` is ignored and stored as 1 (only an *envelope* in `configuration` is refused). | `schemas/strategy.py`, `schemas/backtest.py`; grep of `frontend/src`. | UI cannot tell V1 from V2 except by sniffing JSON (forbidden by the Phase 6 rule), and a client bug could mislabel. |
| **G4** | Validation errors reach the client as one joined string. `ValidationIssue{path,code,message,severity}` exists but is flattened (`StrategyVersionValidationError(f"Invalid V2 definition: {exc}")`); `normalizeDetail` would discard an object detail anyway. | `services/strategy.py:250`, `api/client.ts` | No per-field errors in a rule builder. |
| **G5** | Creation gate ≠ runnable gate. `check_runtime_capabilities=False` at save, `True` at execute. Capability issues have `path == ""` and a text like `implementation: risk.stop_loss`. | `versioning.py` (`load_definition_for_version`), `runtime/capabilities.py` | UI must itself restrict to the runnable subset or get a `runnable` verdict from the server. |
| **G6** | Two ways a document passes *both* gates and fails/misbehaves at run time (probe): **(a)** `rules[].limits` → `UnsupportedOperationError` raised by `RuleEngine` constructor, **after** the dataset was acquired; **(b)** `fill_model` ≠ `same_bar_close` (e.g. `next_bar_open`, `banana`): `parse_environment` only checks "non-empty string"; `SimulatedExecutionAdapter` raises `ExecutionError` later. Both surface as `error_code = market_data_invalid_payload` (the `BacktestExecutionError` default), which is wrong/misleading. **(c)** Timeframe: the definition timeframe is only compared with `backtest_configuration.timeframe` *if that key is present*. A definition with `timeframe:"1w"` and no `timeframe` in `backtest_configuration` ran to completion on the 1d synthetic candles *(probe)*; the dataset request uses `"1d"` regardless. Intraday (`m`/`h`) is refused by the `data.intraday_bars` capability. | `runtime/rules.py` (`limits` check), `runtime/execution.py:106`, `runtime/environment.py` `parse_environment`, `services/backtest.py` (`timeframe` default `"1d"`), `backtesting/reference.py:35` (synthetic provider: only `1d`) | A UI that offered these would produce wrong/misleading results. Until fixed, the UI must pin `timeframe:"1d"` in *both* the definition and `backtest_configuration`, `fill_model:"same_bar_close"`, and never emit `limits`. |
| **G7** | Spec §23 says "creator writes `next_bar_open`"; the shipped runtime supports **only** `same_bar_close`. | spec §23 Phase 6 row vs `execution.py:96-107` | Do not offer a fill-model selector with `next_bar_open`. |
| **G8** | Lifecycle ignores version type. `publish_strategy` takes the latest version regardless; `deploy`/allocation check strategy status only; paper execution reads `version.configuration` with the V1-only `EmaCrossoverPaperAdapter._periods` and fails with `invalid_strategy_configuration`. Marketplace responses do not expose configuration. | `services/strategy.py:374`, `services/allocation.py:136`, `services/execution.py:165`, `paper_execution/reference.py:228` | A V2 strategy can be published/listed/allocated, failing only at execution. **Paper trading and live execution do not support V2.** [Q1] |
| **G9** | No vocabulary/catalog endpoint (spec Phase 7 mentions one). | grep routes | UI would hard-code the vocabulary and could drift from `RUNTIME_CAPABILITIES`. |
| **G10** | Existing V1-shaped UI mis-describes a V2 version: `AlgorithmSummary` falls back to "custom algorithm", `VersionBacktests` states "single-position EMA crossover reference run… Not a general strategy engine", `readEmaRule(configuration)` reads `configuration.entry`. | `ConfigViews.tsx`, `BacktestPages.tsx:141` | Copy and summary need a V2-aware branch keyed on the explicit version. |

Also **[V]**: the pydantic `StrategyVersionCreateRequest` validator (`validate_rule_configuration`) happens to pass a V2
envelope (no `entry`/`exit` keys), so refusal of V2 on the V1 route depends on the service check, not the schema.
`configuration` defaults to `{}` on the V1 route (pre-existing V1 behaviour; unchanged).

---

## 4. Proposed minimum V2 contract **[R]**

Everything under this heading is a **proposal**; none of it exists today. Principles: explicit `definition_schema_version`
on every V2 request and response; separate V2 request models (`extra="forbid"`); one server code path for validation
(the existing loader); no persistence in validate; no change to V1 routes' behaviour for existing clients.

### 4.1 Additive response change (both existing routes) — covers G3

`StrategyVersionResponse` and `BacktestResponse` gain `definition_schema_version: int`
(read from the persisted column / backtest snapshot). Additive; existing clients ignore it. Regenerate
`frontend/src/api/generated/openapi.ts` (`pnpm generate:api-types`; CI checks freshness).

### 4.2 Validate a draft — no persistence — covers G2, G4, G5

`POST /strategies/definitions/validate` (creator role; rate-limited like backtests; stateless — no strategy id needed).

Request:

```json
{
  "definition_schema_version": 2,
  "configuration": { "schema": "algoprofitx.strategy-definition", "schema_version": 2, "timeframe": "1d", "…": "…" },
  "backtest_configuration": { "initial_capital": "100000", "fill_model": "same_bar_close", "timeframe": "1d" }
}
```

Response `200` (always 200 for a well-formed request; validity is in the body):

```json
{
  "definition_schema_version": 2,
  "valid": false,
  "savable": false,
  "runnable": false,
  "issues": [
    { "path": "rules[0].when.left.params.period", "code": "invalid_param", "message": "…", "severity": "error", "layer": "schema|semantic|position|capability|environment" }
  ],
  "required_capabilities": ["indicator.ema@1", "leg.instrument.primary", "leg.side.buy", "op.close", "op.open"],
  "unsupported_capabilities": []
}
```

Semantics: `savable` = loader + L2 + L3 have no `error`; `runnable` = `savable` and capability check and
`parse_environment` pass **and** the G6 fixes below; warnings (e.g. `conflicting_operations`, `hedge_may_outlive_parent`) are
returned with `severity:"warning"` — note `validate_canonical` currently *drops* warnings, so the endpoint must call
`validate_definition` directly. 422 only for a malformed body (wrong `definition_schema_version`, not an object).

### 4.3 Create a V2 version — covers G1

`POST /strategies/{strategy_id}/versions/v2` (route naming alternatives: [Q2]; the shape is what matters):

```json
{
  "definition_schema_version": 2,
  "instrument_id": "20000000-0000-4000-8000-000000000001",
  "configuration": { "…V2 document…" },
  "backtest_configuration": { "initial_capital": "100000", "fill_model": "same_bar_close", "timeframe": "1d", "start_date": "2025-01-01T00:00:00Z" }
}
```

* Model `StrategyVersionV2CreateRequest`, `extra="forbid"`, `definition_schema_version: Literal[2]` **required** (no default).
* Handler = the `create_version` pattern with `create_strategy_version_v2`. **Also require `runnable`** (not just `savable`)
  for UI-created versions, so a user cannot save an unrunnable immutable version [Q3].
* Errors: 404 unknown strategy (existing ownership rule); **422 with structured detail**:

```json
{ "detail": { "code": "invalid_strategy_definition", "message": "The definition is not valid.", "issues": [ { "path": "…", "code": "…", "message": "…", "severity": "error" } ] } }
```

  409 for the existing version-number race / instrument conflicts (unchanged text).
* Response `201`: existing `StrategyVersionResponse` + `definition_schema_version: 2`.
* **V1 route hardening:** `StrategyVersionCreateRequest` gains optional `definition_schema_version: Literal[1] | None`, so a
  body claiming 2 on the V1 route is a 422 rather than silently stored as 1. Existing V1 clients (no field) are unaffected.

### 4.4 Retrieve — no new route

`GET /strategies/{id}`, `GET /strategies/{id}/versions`, `GET /strategies/{id}/versions/{vid}` already return the
configuration; with §4.1 they carry `definition_schema_version`. The UI branches on that field only.

### 4.5 Create and inspect a V2 backtest — no new route

The existing create/execute/get/analytics routes route by the snapshotted version already **[V]**. Example failed row
after the G6 fix: `status:"failed", error_code:"strategy_definition_unsupported_capability", definition_schema_version:2`.
Needed backend adjustments: G6 (a)(b)(c) move into the pre-market-data gate with stable codes (below);
`BacktestCreateRequest` is unchanged.

### 4.6 Optional: vocabulary — covers G9

`GET /strategies/definition-vocabulary` returning the *runnable* subset derived from `RUNTIME_CAPABILITIES` +
`DEFAULT_CATALOG` (indicator specs with param bounds), so the UI cannot drift. If omitted, 7B must hard-code §5 and add a
backend test that fails when `RUNTIME_CAPABILITIES` changes [Q4].

### 4.7 Hardening required to make the contract trustworthy **[R]**

| Id | Change | Why |
|---|---|---|
| H1 | In `parse_environment`: reject unknown `fill_model` (only `same_bar_close`) with `strategy_environment_invalid`. | G6(b) |
| H2 | Make `limits` a capability (`rule.limits`, not provided) or refuse in the pre-run gate, so it fails as `strategy_definition_unsupported_capability` before market data. | G6(a) |
| H3 | Require `backtest_configuration.timeframe` for V2 and equal to the definition timeframe; refuse any timeframe the provider cannot serve with a stable code. | G6(c) |
| H4 | Map runtime `StrategyRuntimeError`s that are *not* data errors to a non-`market_data_*` code (e.g. `strategy_runtime_failed`). | misleading `market_data_invalid_payload` |
| H5 | Block `publish`/`deploy` (or allocation) for `definition_schema_version != 1` with a clear 409, until paper supports V2. | G8 |

H1–H4 change only V2 paths (V1 never reaches them). H5 touches lifecycle and needs a product decision [Q1].

---

## 5. Exact V2 authoring vocabulary the runtime supports **[V]**

Source of truth: `loader.py` (structure), `validation/semantic.py` + `position.py` (meaning),
`runtime/capabilities.py::RUNTIME_CAPABILITIES` = `{op.open, op.close, leg.instrument.primary, leg.side.buy, leg.side.sell, short_sell, indicator.ema@1}`,
`runtime/rules.py`, `runtime/market.py`, `runtime/execution.py`. "Runs" = verified by probe through `StrategyRuntimeEngine`.

### 5.1 Envelope and document

```json
{
  "schema": "algoprofitx.strategy-definition",
  "schema_version": 2,
  "timeframe": "1d",
  "evaluation": "bar_close",
  "positions": { "<position_id>": { … } },
  "rules": [ { … } ]
}
```

Closed objects: unknown keys are errors; nothing is defaulted. Ids (`ID_PATTERN` `^[a-z0-9][a-z0-9_-]{0,63}$`) are one namespace across
positions, legs and rules.

| Field | Authorable value (runnable) |
|---|---|
| `timeframe` | **`"1d"` only** (see G6; intraday refused; provider serves 1d only). |
| `evaluation` | `"bar_close"` |
| `positions` | **exactly one** position, `role:"core"`, `hedges:null`, **exactly one** leg |
| leg | `{id, instrument:{kind:"primary"}, side:"buy"\|"sell", quantity:<positive>, role?}` ; `sell` = short (supported; probe) |
| `sizing` | `{unit:"shares", value:<positive>}`; order qty = `sizing.value × leg.quantity` (probe: leg qty 2 doubled P&L) |
| `rules` | ≥1 rule |
| rule | `{id, when, then:[…], label?, when_position?, priority?}` |
| `when_position` | map `positionId → "flat"\|"open"` (`"open"` requires some rule to open it) |
| `priority` | integer; lower runs first; default 0, ties by declaration order |
| `then` | non-empty list of `{op:"open"\|"close", position:<id>}` — **no `amount`** |

### 5.2 Conditions (all supported by loader, evaluator and runtime; probe for `edge`, `not`, `all`, `compare`, `cross`)

| Node | Shape | Notes |
|---|---|---|
| `compare` | `{kind, op:"gt"\|"gte"\|"lt"\|"lte"\|"eq", left, right}` | `eq` is **rejected** when either side is a price/indicator series; `eq` only constant-vs-constant (pointless). Offer `gt/gte/lt/lte`. |
| `cross` | `{kind, dir:"above"\|"below", left, right}` | needs at least one series side. Needs previous bar → UNKNOWN (no fire) during warm-up. |
| `all` / `any` | `{kind, of:[cond,…]}` | non-empty; nesting depth ≤ 16 |
| `not` | `{kind, of:cond}` | |
| `edge` | `{kind, dir:"rising", of:cond}` | true on the bar the inner condition becomes true |

Three-valued logic: UNKNOWN (warm-up/missing) never fires a rule.

### 5.3 Operands

| Operand | Shape | Runnable |
|---|---|---|
| price | `{kind:"price", field:"open"\|"high"\|"low"\|"close"\|"volume"}` | yes (probe, incl. `volume` vs constant). Compare units: price vs price, volume vs volume; mixing is `incompatible_operands`. |
| constant | `{kind:"constant", value:<number or decimal string>}` | yes |
| indicator | `{kind:"indicator", name:"ema", version:1, params:{period:int 1–5000}, source:{kind:"price",field:<open\|high\|low\|close>}, timeframe:"1d", output:"value"}` | **`ema@1` only**; `source` must be a **price field, not `volume`**, and `timeframe` must equal the definition timeframe. |

### 5.4 What the *save* gate additionally accepts but the runtime refuses (do not author)

`sma@1`, `rsi@1` (in the catalog; no runtime calculation → `capability_missing`, probe), indicator `source` that is an
indicator or `volume`, indicator timeframe ≠ definition timeframe.

### 5.5 Backtest environment (`backtest_configuration`) the V2 path reads

| Key | Rule |
|---|---|
| `initial_capital` | required; positive number or numeric string |
| `fill_model` | required for V2; **only `"same_bar_close"`** works (fills at the signal bar's close, at its timestamp) |
| `timeframe` | UI must send `"1d"` (G6c) |
| `start_date` / `end_date` | optional ISO datetimes; read by `create_backtest` for the dataset window (UTC-normalised; defaults 2025-01-01 + 120 days). Subject to calendar/market-data limits [V]; `adjustment_policy` only `"unadjusted"` |

### 5.6 Execution realities worth showing the author **[V]**

Synthetic reference data only (`synthetic-local-v1`); daily bars; any position still open after the last candle is
liquidated (`exit_reason:"end_of_data"`); V2 trade records add `position`, `leg`, `signal_timestamp`, `fill_timestamp`,
`exit_fill_timestamp`, `exit_reason`, optional `exit_signal_timestamp`; result limits 100 trades / 256 equity points
(`MAX_RESULT_*`). Engine identifier `strategy-runtime-v2`. Analytics endpoint works on this summary shape (no engine check).

---

## 6. Explicitly unsupported — the frontend must not offer these **[V]**

| Capability | State in code | Behaviour if sent |
|---|---|---|
| `op: increase`, `op: reduce` (+ `amount`) | loader/semantic accept; runtime lacks `op.increase`/`op.reduce` | `capability_missing` at execute |
| Rule `limits.max_fires_per_position` | loader accepts; **no capability gate** | fails mid-run, wrong code (G6a) |
| `risk.stop_loss`, `risk.take_profit` (percent of `leg_price`) | loader accepts | `capability_missing` |
| Trailing risk, `position_pnl_*`, `underlying_price`, `net_premium` bases | reserved → loader error `unsupported_kind` | rejected at save |
| Multi-leg positions | `multi_leg.basket` missing | `capability_missing` |
| Hedge positions, multiple core positions | `positions.hedge`, `positions.multiple_core` missing | `capability_missing` |
| Instrument selectors other than `primary` (future/option) | reserved → `unsupported_kind` | rejected at save |
| Sizing `contracts`, `lots`, `match_position` | reserved → `unsupported_kind` | rejected |
| `percent_of_allocation` sizing | **V1-adapter-only** | rejected (`sizing_not_authorable`) |
| `shares` sizing as % of capital / risk-based sizing | does not exist | — |
| Indicators other than `ema@1` (`sma@1`, `rsi@1` exist in the catalog but not in the runtime; no VWAP/Bollinger/etc.) | see §5.4 | `capability_missing` |
| Intraday timeframes (`m`, `h`) | `data.intraday_bars` missing; provider is 1d only | `capability_missing` |
| Timeframes `Nd` (N>1) / `w` | pass all gates; run silently on 1d candles | **wrong** (G6c) — do not offer |
| Indicator on another timeframe than the definition | runtime refuses | `RuntimeSetupError` |
| Reserved conditions `within`, `for_bars`; reserved operands `position`, `arith` | loader `unsupported_kind` | rejected at save |
| Reserved ops `replace`, `adjust` | loader `unsupported_kind` | rejected |
| Fill model `next_bar_open` (and any other) | not implemented | wrong code mid-run (G6b) |
| Evaluation other than `bar_close` | rejected | — |
| Margin/leverage, fees, slippage, tick/lot rounding, persisted position state | not implemented | n/a |
| **Paper trading and live broker execution for V2** | paper adapter is V1-only; no live adapter | G8. The UI must not imply V2 can be paper-traded, allocated, or run live. |

---

## 7. Required frontend screens and components **[R]**

### 7.1 Screens (all under the existing `creator/strategies/:strategyId/…` area)

1. **V2 Version Creator** (new mode beside the V1 form): instrument → timeframe (fixed `1d`, shown read-only) → position & leg (side,
   shares) → rule builder (entry, exit) → capital (fixed `same_bar_close`, shown) → review → save.
2. **Validation panel** (live, debounced call to §4.2) listing issues by path; save disabled until `runnable`.
3. **Review/confirm** step stating that the version is immutable (reuse `ConfirmDialog`).
4. **Version detail** branching on `definition_schema_version`: V2 plain-language rule describer + technical JSON (existing
   `TechnicalDetails`).
5. **Backtest** panels reuse `VersionBacktests`/`BacktestDetailPage`, with V2-correct engine copy and V2 trade fields.
6. **Lifecycle copy:** for V2, a visible "Backtest only — not available for paper trading" notice (see [Q1]).

### 7.2 Components

| Need | Existing reusable | Gap |
|---|---|---|
| Fields | `components/ui/Input` (label/hint/error), `form-field`/`field-error`/`field-hint` CSS, `FormError`, `react-hook-form` + `zod` already dependencies | `Select`, number/decimal input with unit adornment |
| Errors | `Alert` (`variant="error"`), `ErrorPanel` (retry), `InlineStatus`, `useToast` | **issue list bound to a `path`** (new) |
| Confirm | `ConfirmDialog`, `Dialog` | — |
| Layout | `PageHeader`, `SectionHeader`, `Card`, `Tabs`, `form-section` numbered sections already used by `VersionCreator`, `detail-layout`, `page-stack` | stepper (optional) |
| Loading / empty | `Skeleton*`, `LoadingState`, `EmptyState` (`PageState.tsx`) | — |
| Theming | Semantic CSS tokens only (`styles/tokens.css`; dark/light under `data-theme`, `ThemeProvider`, `lib/theme.ts`). Components must use tokens, never hard-coded colours | — |
| Rule builder | none | **recursive condition tree editor** (all/any/not/compare/cross/edge), operand picker, indicator picker; keyboard accessible; collapses on mobile (existing styles use responsive CSS in `creator.css`, `workspace.css`) |
| Describer | `strategyConfig.ts` `describe*` pattern (V1 only) | `v2Describe.ts` turning a definition into plain language |
| API types | `api/types.ts` re-exports from generated OpenAPI | regenerate after §4 backend work |

### 7.3 Client-side changes

* `normalizeDetail` must understand `{detail:{code,message,issues[]}}` and expose `ApiError.issues` (additive; string/array
  paths and existing tests unchanged).
* `queryKeys` additions for the validate mutation are not needed (mutation only); reuse `versions`/`version` keys.
* A single `isV2(version)` helper reading only `definition_schema_version === 2`; never inspect `configuration`.

---

## 8. V1 compatibility and migration safeguards

**[V] already in place:** the persisted column is the only selector; `resolve_schema_version` has no fallback for unknown
values; legacy rows backfill to 1 with no JSON rewrite; backtests snapshot the version; V1 execution path
(`EmaCrossoverReferenceEngine`) is unchanged and asserted untouched by `test_v1_never_touches_the_v2_runtime`;
the V1 route refuses a V2 envelope; Phase 5 parity fixtures prove the runtime reproduces V1 results.

**[R] for 7B:**

1. V1 creation form, `strategyConfig.ts`, `buildConfiguration`, `readEmaRule` and their tests stay untouched; V2 is a separate
   code path chosen **explicitly by the author** ("Classic EMA" vs "Rule builder"), never inferred.
2. Every V2 request and response carries `definition_schema_version`; V2 request models `extra="forbid"`; the UI sends `2` and
   asserts the response says `2` (fail loudly otherwise).
3. No automatic conversion of V1 versions into V2 documents; "duplicate as V2" can be a later, separate decision. The
   V1 adapter lifts *in memory only*; never write its output back.
4. No data migration, no `CHECK` constraint change, no new column in 7B.
5. Gate V2 UI behind a feature flag (config) so it can ship dark; `definition_schema_version` additions are safe to ship
   regardless.
6. Regression tests (below) assert V1 request/response byte-compat apart from the one additive field.

---

## 9. Phase 7B implementation and test plan **[R]**

Split into two PRs so the contract is settled and tested before UI work.

### 7B-1 Backend contract (small; V2 paths only except additive response field)

1. `definition_schema_version` on `StrategyVersionResponse` / `BacktestResponse`; V1 route `Literal[1] | None` field.
2. `POST /strategies/definitions/validate` and `POST /strategies/{id}/versions/v2` (final path per [Q2]); structured 422.
3. H1–H4 hardening (and H5 if decided). No new capabilities, no schema expansion.
4. Optional vocabulary endpoint ([Q4]).

Tests (pytest, mirroring `test_strategy_v2_service_wiring.py`):

* validate: valid ema crossover → `valid/savable/runnable` true; `sma@1` → `savable` true, `runnable` false, capability issue;
  `limits` → not runnable; `next_bar_open` → not runnable; `1w` → not runnable; malformed → per-path issues; warnings preserved;
  nothing persisted (row counts); non-creator 403; unauthenticated 401; rate limit.
* create-V2: persists `definition_schema_version == 2`, returns it, configuration byte-identical; missing/`1`/`"2"` field → 422;
  extra field → 422; V1 envelope-less JSON → 422; another creator's strategy → 404; invalid instrument → 422.
* V1 route: body with `definition_schema_version: 2` → 422; V1 body unchanged → 201 with `definition_schema_version: 1`.
* Backtest: created from a V2 version returns `definition_schema_version: 2`; the failure codes in §4.7; V1 backtest path
  still asserts the V2 runtime is never touched.
* Regenerate OpenAPI types; CI "types fresh" check passes.

### 7B-2 Frontend (after 7B-1 merges; no backend change)

1. `normalizeDetail`/`ApiError.issues` + tests; `isV2` helper; `strategiesApi.validateDefinition`, `createVersionV2`.
2. `v2Definition.ts`: typed builder from form state → document (only §5 vocabulary), pure functions with unit tests
   (round-trip against `validate`, golden documents equal to the fixtures in `tests/strategy_v2_builders.py`).
3. Rule builder, validation panel, review/confirm, V2 version detail + describer, V2 copy in `VersionBacktests`,
   lifecycle notice. Component tests (Vitest + Testing Library, as in `StrategyBuilder.test.tsx`), keyboard/aria checks,
   light/dark and 375px layout checks.
4. Existing suites must pass unchanged (`pnpm test`, `pnpm typecheck`, `pnpm build`).

---

## 10. Open questions and blockers

| Id | Question / blocker | Recommendation |
|---|---|---|
| **Q1** | **Blocker for shipping the creator:** may a V2 strategy be published/deployed/allocated while paper trading cannot run it (G8)? | Block V2 at publish (H5) or hide lifecycle actions for V2 in the UI **and** enforce server-side. Needs a product decision. |
| Q2 | Final route shape: dedicated `/versions/v2` vs one `/versions` endpoint discriminated by `definition_schema_version`. | Dedicated route + V1 hardening (cleanest for `extra="forbid"` and OpenAPI types). |
| Q3 | Should saving require `runnable` (stricter than the service's `savable`)? | Yes for the UI route; keep the internal service permissive for future-capability tests. |
| Q4 | Serve the vocabulary from the backend or hard-code it in the UI? | Serve it (small, read-only); else add a drift test. |
| Q5 | `start_date`/`end_date` authoring: expose date pickers? Calendar/market-data windows are server-limited and the provider is synthetic. | Defer; omit dates in 7B so server defaults apply, or expose only after confirming limits. |
| Q6 | Spec says creators write `next_bar_open` (§23). Should 7B show a fixed, read-only `same_bar_close`? | Yes, with copy explaining the assumption; revisit when `next_bar_open` ships. |
| Q7 | Is `eq` on constants worth offering? | No; offer `gt/gte/lt/lte` only. |

No blocker prevents the *7B-1 backend contract* PR. The UI (7B-2) is blocked only on 7B-1 and on Q1.
