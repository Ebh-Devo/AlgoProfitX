# Catalyst Auth Session Development Schema

Provision these tables in the **Development** environment only. Public API
session IDs remain application UUIDs; Catalyst `ROWID` values stay internal.

## `AlgoProfitXAuthSessions`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `session_uuid` | Var Char | 36 | Yes | Yes |
| `user_uuid` | Var Char | 36 | Yes | No |
| `slot_key` | Var Char | 64 | Yes | No |
| `refresh_token_hash` | Var Char | 64 | Yes | No |
| `created_at` | Var Char | 40 | Yes | No |
| `expires_at` | Var Char | 40 | Yes | No |
| `rotated_at` | Var Char | 40 | No | No |
| `revoked_at` | Var Char | 40 | No | No |
| `last_used_at` | Var Char | 40 | No | No |

## `AlgoProfitXRefreshClaims`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `claim_hash` | Var Char | 64 | Yes | Yes |
| `session_uuid` | Var Char | 36 | Yes | No |
| `claimed_at` | Var Char | 40 | Yes | No |

## `AlgoProfitXAuthSessionSlots`

| Column | Type | Max length | Mandatory | Unique |
| --- | --- | ---: | --- | --- |
| `slot_key` | Var Char | 64 | Yes | Yes |
| `slot_index` | Var Char | 3 | Yes | No |
| `user_uuid` | Var Char | 36 | Yes | No |
| `session_uuid` | Var Char | 36 | Yes | Yes |
| `assigned_at` | Var Char | 40 | Yes | No |

`claim_hash` is the SHA-256 digest of a consumed refresh token. Its native
unique constraint is the atomic winner for refresh rotation. A second claim
for the same token is treated as reuse and revokes the session. If the session
update fails after a claim succeeds, that token remains consumed and the
operation fails closed.

The service generates the application session UUID before creating the row,
then derives and hashes the refresh token from that UUID. Plaintext refresh
tokens never cross the repository boundary.

The adapter creates at most the configured number of deterministic, native-
unique slot keys per user. A session is valid only while it owns its slot. At
capacity, creation removes the oldest slot before claiming it for the new
session, so concurrent logins can invalidate an extra fresh login under heavy
contention but cannot increase the active-session bound. A failed session
insert compensates by deleting its claimed slot. Refresh claims should later be expired by a
durable maintenance job after their associated session expiry and security
retention window.
