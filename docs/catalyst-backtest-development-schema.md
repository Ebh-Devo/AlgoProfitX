# Catalyst Development backtest schema

The Development backtest queue uses three Catalyst Data Store tables. JSON and
timestamps are stored as bounded text so values round-trip without floating-point
or timezone loss.

## `AlgoProfitXBacktests`

| Column | Type | Required | Unique |
| --- | --- | --- | --- |
| `backtest_uuid` | Var Char (36) | yes | yes |
| `request_key` | Var Char (64) | yes | yes |
| `strategy_uuid` | Var Char (36) | yes | no |
| `strategy_version_uuid` | Var Char (36) | yes | no |
| `instrument_uuid` | Var Char (36) | no | no |
| `requested_by_uuid` | Var Char (36) | yes | no |
| `status` | Var Char (20) | yes | no |
| `configuration_snapshot` | Text (10000) | yes | no |
| `backtest_configuration_snapshot` | Text (10000) | yes | no |
| `instrument_snapshot` | Text (10000) | no | no |
| `market_data_reference` | Text (10000; application limit 500) | no | no |
| `market_data_provider` | Var Char (100) | no | no |
| `dataset_reference` | Text (10000; application limit 500) | no | no |
| `timeframe` | Var Char (50) | yes | no |
| `range_start`, `range_end` | Var Char (40) | no | no |
| `adjustment_policy` | Var Char (50) | yes | no |
| `data_fetched_at` | Var Char (40) | no | no |
| `market_data_provenance`, `result_summary` | Text (10000) | no | no |
| `error_message` | Text (10000; application limit 500) | no | no |
| `error_code` | Var Char (100) | no | no |
| `attempt_count` | BigInt | yes | no |
| `lease_token` | Var Char (64) | no | no |
| `lease_expires_at`, `created_at`, `started_at`, `completed_at` | Var Char (40) | as applicable | no |

## `AlgoProfitXBacktestClaims`

| Column | Type | Required | Unique |
| --- | --- | --- | --- |
| `claim_key` | Var Char (64) | yes | yes |
| `lease_token` | Var Char (64) | yes | yes |
| `backtest_uuid` | Var Char (36) | yes | no |
| `attempt_number` | BigInt | yes | no |
| `claimed_at`, `expires_at` | Var Char (40) | yes | no |

Each attempt has a deterministic unique claim key. Concurrent workers therefore
cannot own the same attempt. Expired leases create the next attempt, preserving an
append-only audit trail.

## `AlgoProfitXBacktestTerminals`

| Column | Type | Required | Unique |
| --- | --- | --- | --- |
| `backtest_uuid` | Var Char (36) | yes | yes |
| `terminal_key` | Var Char (64) | yes | yes |
| `status` | Var Char (20) | yes | no |
| `result_summary` | Text (10000) | no | no |
| `error_message` | Text (10000; application limit 500) | no | no |
| `error_code` | Var Char (100) | no | no |
| `market_data_provider` | Var Char (100) | no | no |
| `dataset_reference` | Text (10000; application limit 500) | no | no |
| `data_fetched_at` | Var Char (40) | no | no |
| `market_data_provenance` | Text (10000) | no | no |
| `completed_at` | Var Char (40) | yes | no |
| `lease_token` | Var Char (64) | yes | no |

The unique terminal receipt is the authoritative outcome. Reads repair an
incomplete projection update after a process interruption.

## Durable execution

`AlgoProfitXBacktests` is also the name of the Development AppSail Job Pool.
The application pins the Development pool and AppSail target IDs so a renamed
resource cannot silently redirect work.
The execute endpoint submits an immediate job targeting
`algoprofitx-api:/internal/backtests/process`. Catalyst owns job delivery and
retries, while the claim and terminal tables make repeated delivery safe.
