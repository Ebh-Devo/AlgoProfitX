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

The initial repository slice supports owned draft CRUD only. Lifecycle,
versions, history protection, and their atomic command tables are added before
the public Development strategy routes switch to Catalyst.
