# Catalyst Identity Development Schema

This schema is for the `Users / Roles / Registration / Auth` migration slice.
Create and validate it in Catalyst **Development** before enabling the Catalyst
identity repository. Do not create or enable it in Production until the full
Development auth gate passes.

## Tables

### `AlgoProfitXRoles`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `role_name` | Var Char | 50 | Yes | Yes |

Seed exactly two rows: `INVESTOR` and `CREATOR`.

### `AlgoProfitXUsers`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `user_uuid` | Var Char | 36 | Yes | Yes |
| `email_lookup` | Var Char | 64 | Yes | Yes |
| `email` | Text | 10000 | Yes | No |
| `password_hash` | Var Char | 255 | Yes | No |
| `is_active` | Boolean | — | Yes | No |
| `is_verified` | Boolean | — | Yes | No |
| `role_names` | Var Char | 100 | Yes | No |
| `full_name` | Var Char | 150 | No | No |
| `phone` | Var Char | 30 | No | No |
| `created_at` | Var Char | 40 | Yes | No |
| `updated_at` | Var Char | 40 | Yes | No |

`ROWID`, `CREATORID`, `CREATEDTIME`, and `MODIFIEDTIME` are Catalyst-managed
columns and must not be recreated.

## Integrity and security contract

- `email_lookup` is the SHA-256 digest of the normalized email. The repository
  uses this fixed-format value in ZCQL, so user-provided text is never joined
  into a query. The native unique constraint is the registration race guard.
  The application still enforces the public 320-character email limit; `Text`
  is required because Catalyst `Var Char` is limited to 255 characters.
- `user_uuid` remains the public application identifier. Catalyst `ROWID` stays
  internal.
- `password_hash` contains the existing Argon2 hash. Plaintext passwords never
  enter the persistence adapter.
- Role membership is embedded in the user row. Registration therefore creates
  the user, profile fields, and default `INVESTOR` membership in one insert.
- Creator enrollment is idempotent. The role catalog is checked before the
  membership update.
- Timestamps are UTC ISO-8601 strings with offsets. This avoids depending on
  provider-specific timestamp serialization at the domain boundary.

Auth-session tables and the atomic refresh-token claim design belong to the
next focused slice. The Catalyst identity backend must remain disabled until
those tables, adapters, and real Development auth smoke tests are complete.

The Development-only `POST /health/catalyst/identity` probe registers a
generated disposable identity, validates hashed lookup and password checking,
adds the creator role, deletes the identity, and verifies cleanup. It returns
only PASS/FAIL stages and is unavailable in Production.
