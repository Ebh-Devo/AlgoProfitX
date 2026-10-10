# Catalyst Instrument Development Schema

Catalyst owns the standard system columns. The following application columns
are provisioned in Development.

## `AlgoProfitXExchanges`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `exchange_uuid` | Var Char | 36 | Yes | Yes |
| `code` | Var Char | 20 | Yes | Yes |
| `name` | Var Char | 150 | Yes | No |
| `country_code` | Var Char | 2 | Yes | No |
| `timezone` | Var Char | 100 | Yes | No |
| `default_currency` | Var Char | 3 | Yes | No |
| `calendar_code` | Var Char | 50 | Yes | No |
| `is_active` | Boolean | n/a | Yes | No |
| `created_at` | Var Char | 40 | Yes | No |
| `updated_at` | Var Char | 40 | Yes | No |

## `AlgoProfitXInstruments`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `instrument_uuid` | Var Char | 36 | Yes | Yes |
| `exchange_uuid` | Var Char | 36 | Yes | No |
| `canonical_symbol` | Var Char | 100 | Yes | No |
| `canonical_lookup` | Var Char | 64 | Yes | Yes |
| `exchange_symbol` | Var Char | 100 | Yes | No |
| `exchange_symbol_key` | Var Char | 64 | Yes | No |
| `name` | Var Char | 200 | Yes | No |
| `instrument_type` | Var Char | 20 | Yes | No |
| `quote_currency` | Var Char | 3 | Yes | No |
| `tick_size` | Var Char | 40 | No | No |
| `lot_size` | BigInt | n/a | No | No |
| `is_tradeable` | Boolean | n/a | Yes | No |
| `isin` | Var Char | 12 | No | No |
| `is_synthetic` | Boolean | n/a | Yes | No |
| `is_active` | Boolean | n/a | Yes | No |
| `created_at` | Var Char | 40 | Yes | No |
| `updated_at` | Var Char | 40 | Yes | No |

The repository hashes canonical and venue-scoped symbol identities before any
lookup key is persisted. Catalyst currently permits two unique varchar columns
per table, so native uniqueness protects the application UUID and canonical
symbol hash. The catalog has no public write API; deterministic bootstrap IDs
and idempotent reads protect the remaining seed identities.
