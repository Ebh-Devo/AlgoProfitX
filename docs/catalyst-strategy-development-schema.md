# Catalyst Strategy Development Schema

Provision this table in the Catalyst **Development** environment before enabling
the Catalyst strategy repository. Catalyst owns the standard `ROWID`,
`CREATORID`, `CREATEDTIME`, and `MODIFIEDTIME` columns.

## `AlgoProfitXStrategies`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `strategy_uuid` | Var Char | 36 | Yes | Yes |
| `creator_uuid` | Var Char | 36 | Yes | No |
| `name` | Var Char | 150 | Yes | No |
| `slug` | Var Char | 180 | Yes | No |
| `slug_lookup` | Var Char | 64 | Yes | Yes |
| `description` | Text | 10000 | No | No |
| `status` | Var Char | 20 | Yes | No |
| `is_public` | Boolean | n/a | Yes | No |
| `current_version_uuid` | Var Char | 36 | No | No |
| `created_at` | Var Char | 40 | Yes | No |
| `updated_at` | Var Char | 40 | Yes | No |
| `published_at` | Var Char | 40 | No | No |
| `deployed_at` | Var Char | 40 | No | No |

`strategy_uuid` remains the public API identifier. `slug_lookup` is the SHA-256
lookup key used by ZCQL, so user-provided slug text is never interpolated into a
query. Native uniqueness on both identifiers is required for race-safe create
and slug update behavior.

## `AlgoProfitXStrategyVersions`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `version_uuid` | Var Char | 36 | Yes | Yes |
| `strategy_uuid` | Var Char | 36 | Yes | No |
| `version_key` | Var Char | 64 | Yes | Yes |
| `instrument_uuid` | Var Char | 36 | Yes | No |
| `version_number` | BigInt | n/a | Yes | No |
| `configuration` | Text | 10000 | Yes | No |
| `backtest_configuration` | Text | 10000 | Yes | No |
| `instrument_snapshot` | Text | 10000 | Yes | No |
| `created_at` | Var Char | 40 | Yes | No |

Version records are immutable. `version_key` is SHA-256 of the strategy UUID
and server-allocated version number. Its native uniqueness is the final guard
against concurrent allocation. The instrument snapshot contains only the safe
public instrument and exchange fields returned by the API; provider mappings
and credentials are never stored in it.

## `AlgoProfitXStrategyLocks`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `strategy_uuid` | Var Char | 36 | Yes | Yes |
| `owner_token` | Var Char | 64 | Yes | Yes |
| `acquired_at` | Var Char | 40 | Yes | No |

The lock row serializes version allocation and lifecycle transitions. A unique
strategy UUID permits one owner, the opaque token protects release ownership,
and a bounded stale-lock recovery path prevents a terminated request from
blocking the aggregate permanently.
