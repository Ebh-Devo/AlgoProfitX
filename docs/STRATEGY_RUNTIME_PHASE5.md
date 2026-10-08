# Strategy V2 — Phase 5 runtime: implementation note

Implements Phase 5 of [STRATEGY_DEFINITION_V2.md](STRATEGY_DEFINITION_V2.md) §23. Opt-in and
unwired: no API, database, UI or backtest-service change; `EmaCrossoverReferenceEngine` is
untouched and remains the parity oracle.

## Module boundary — `backend/app/strategy_definition/runtime/`

| Module | Responsibility |
|---|---|
| `state.py`, `state_machine.py` | immutable pre-bar snapshot; pure status derivation and operation preconditions |
| `rules.py` | conditions → position **operations** (existing evaluator; TRUE fires, UNKNOWN does not) |
| `operations.py`, `conflicts.py` | operation/source types; per-position `close > reduce > increase > open` resolution |
| `intents.py`, `planner.py` | `OrderIntent`, deterministic ids; operation → intents (side, size, contract) |
| `execution.py` | `ExecutionAdapter` seam, `ExecutionEvent`, `SimulatedExecutionAdapter` (`same_bar_close`) |
| `ledger.py` | the only owner of holdings, cash, P&L, trade lifecycle and position status |
| `market.py`, `capabilities.py`, `environment.py` | validated bars + causal indicator series; provided capabilities; environment config and pre-run gate |
| `runtime.py`, `engine.py` | per-bar orchestration; `StrategyRuntimeEngine` behind the `BacktestEngine` protocol |

Pipeline per completed bar `t`: pre-bar snapshot → rules (priority, then declaration order) →
conflict resolution → planner → execution adapter → ledger.

## Boundaries that matter

* **Intent / event.** The planner emits `OrderIntent` (no broker fields). The adapter returns
  `ExecutionEvent`s (`accepted`, `rejected`, `partial_fill`, `filled`, `cancelled`, `expired`;
  `filled_qty` is per event). The ledger changes holdings **only** from events;
  `track_order` registers a working order and changes no quantity.
* **Ledger truth.** `open` is never set by an operation. `flat/opening/open/closing/degraded` is
  derived from held quantity, fixed leg ratios and working orders.
* **Identity.** `intent_id = sha256(canonical JSON of scheme, strategy_version_id, source kind/id,
  bar_ts (UTC), op_index, leg_id)`; no UUID, clock or randomness. The canonical form is pinned by a test.
* **Environment, not definition.** Capital, fill model and `strategy_version_id` come from
  `backtest_configuration` / the engine constructor. A V2 run must name its `fill_model`; a lifted V1
  document carries `same_bar_close`.

## Parity fixture

`backend/tests/fixtures/strategy_v2_runtime_parity.json` (regenerate with
`python -m tests.strategy_v2_runtime_support`) locks, per Phase 1 case, the V1 engine record and the
runtime record: signal/fill timestamps, side, quantity, entry/exit price, P&L, exit reason, final
equity and the full equity curve. The V1 half is also asserted equal to the independently committed
Phase 1 `strategy_v2_parity.json`, so regenerating cannot weaken V1's expected values. Exit-reason
mapping: `rule:exit` for the exit rule; `end_of_data` for the engine-issued close of a position still
held after the final candle (no signal timestamp).

## Deferred (reserved, refused with a structured error — never ignored)

`increase`, `reduce`, `limits`, risk exits, multi-leg, hedges, multiple positions, indicators other
than `ema@1`, indicator timeframes other than the definition's, `next_bar_open`, lot/tick rounding,
persisted state, paper/live adapters, backtest-service/API selection of this engine.
