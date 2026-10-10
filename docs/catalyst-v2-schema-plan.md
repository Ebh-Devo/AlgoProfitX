# Catalyst schema plan for Strategy V2 (`definition_schema_version`)

**Status: PROPOSED. NOT APPROVED. NOT APPLIED.** No live Data Store table has been or will be changed
without explicit approval. Until then the application is fail-closed: V1 works unchanged and V2
writes/backtests return 503 `strategy_definition_v2_storage_unavailable` (nothing is stored).

## What the Catalyst documentation states (and does not)

Sources: [Data Store columns](https://docs.catalyst.zoho.com/en/cloud-scale/help/data-store/columns/) and
[ZCQL V2 syntax and exceptions](https://docs.catalyst.zoho.com/en/cloud-scale/help/zcql/syntax-exceptions/)
(read 2026-10-10). No live table was probed or written to.

| Question | Documented answer |
|---|---|
| Text column limit | **10,000 characters** (Var Char: 255). Over-length VarChar raises an error (example: `'salmon' data too long for column`). |
| Int / BigInt | Int is 4-byte, up to 10 digits (ZCQL errors outside -9999999999..9999999999); BigInt is 8-byte, up to 19 digits. |
| Default value | Available for all column types **except Text**; applied "if the value for a column is left empty". |
| Edit after creation | **Data type and `IsUnique` cannot be changed.** Var Char max length can only increase. Other attributes are not listed. |
| Column limit | 100 columns per table in Development; no upper limit in Production. |
| Existing rows when a column is added | **Not stated.** |
| Mandatory column on a populated table | **Not stated.** |
| Unknown column in a `SELECT` | **Not documented.** (An unknown column in `WHERE` is documented as `Unknown Table ... or Unknown Column ... in WHERE`.) |
| Production schema changes | The console says "You cannot do any configuration changes here" in Production; how Development schema reaches Production is **not verified** here. |

Consequences for the design: the code never assumes backfill (a missing, `NULL` or blank value reads as V1); the
column is created **not mandatory**; the data type is chosen correctly the first time because it cannot be
edited; and the unknown-column behavior is handled without relying on a specific error (see Detection).

## Proposed change (Development console, after approval)

Add one column to **each** of `AlgoProfitXStrategyVersions` and `AlgoProfitXBacktests`:

| Setting | Value | Why |
|---|---|---|
| Column name | `definition_schema_version` | exact name the code reads and writes |
| Data type | **Int** | values are 1 or 2; BigInt unnecessary; type cannot be edited later |
| Default value | `1` | existing code semantics (a missing value is V1) |
| Is mandatory | **off** | mandatory-on-populated-table behavior is undocumented; the code does not need it |
| Is unique | **off** | cannot be changed later; never used for lookup |
| Search index | off | never filtered on |
| PII/ePHI | off | not personal data |

`BacktestTerminals` and every other table are unchanged. No row is rewritten.

## Detection in the application (already implemented, tested with doubles)

`persistence/catalyst/schema.py` probes read-only with `SELECT ROWID, definition_schema_version FROM <table> LIMIT 1`:

- success -> column present (cached 5 min); two consecutive failures **and** a readable table -> absent (cached 30 s);
- unreadable table -> outage, surfaced, never cached as "absent";
- a column once seen present is never downgraded to absent (a transient blip must not make V2 rows read as V1).

**Verified live (read-only, Development ZCQL Console, 2026-10-10):** a `SELECT` of the not-yet-existing column on
`AlgoProfitXStrategyVersions` is rejected with `Unkown Table AlgoProfitXStrategyVersions or Unkown Column definition_schema_version in SELECT`
(sic), exactly the failure the probe treats as "column absent". (Had Catalyst answered without error, the probe would report "present" and
the V2 insert would then fail with a generic persistence error: still fail-closed, never stored as V1.) Runbook pre-check 1 below is
therefore already answered for the unknown-column error text; the row-count and post-change reads still apply.

## Runbook (after approval; Development only)

1. **Pre-checks (read-only, ZCQL console):** record `SELECT COUNT(ROWID)` for both tables; run
   `SELECT ROWID, definition_schema_version FROM AlgoProfitXStrategyVersions LIMIT 1` *before* the change and record the
   exact error text (this documents the undocumented behavior).
2. Confirm no V2 writes have been attempted (they cannot succeed while the column is absent).
3. Add the column to `AlgoProfitXStrategyVersions`, then `AlgoProfitXBacktests`, with the settings above.
4. **Verify in Schema View** (type Int, default 1, not mandatory, not unique) and re-run the console `SELECT`; record how an
   existing row reads (`NULL`, missing or `1`). All are handled as V1.
5. Wait up to 5 minutes (probe cache) or redeploy; no code change is needed.
6. **Smoke (throwaway user):** create a V2 version (201, stored as `2`); backtest it (completes); publish/deploy/allocate it
   (409 `strategy_definition_version_unsupported_for_execution`); create a V1 version (stored as `1`); confirm existing V1
   versions and backtests still list and execute.
7. How the schema reaches Production is a separate, explicitly approved step (the Production console blocks configuration edits).

## Rollback

The column is additive and harmless to leave. To roll back, revert the application release (V2 writes then stop being possible
through the product); **do not drop the column while any row holds a value other than 1**, and never drop-and-recreate a table
with data. If the type or defaults were wrong, add a new column and a code change; the type cannot be edited in place.

## Size limits to keep in mind

Text columns hold 10,000 **characters**; the repository enforces 10,000 **UTF-8 bytes** (never larger than the character count),
so a stored value always fits. This applies to `configuration`, `backtest_configuration`, `instrument_snapshot`,
`result_summary` and `market_data_provenance`. V2 definitions are about 1 KB in the test fixtures, but nesting up to 16 levels
is allowed, so an oversized definition is rejected with a clear validation error before any write. Measured backtest results are
about 5 KB (64 equity points, few trades); a result that does not fit fails **terminally** with `backtest_result_too_large`
(not retried). Real market data with many trades will need File Store or a trimmed summary; that is future work.
