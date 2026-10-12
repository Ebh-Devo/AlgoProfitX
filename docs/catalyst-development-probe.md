# Catalyst Development Probe

This is a disposable connectivity gate. It does not migrate application
tables or switch the production persistence backend.

## Development Table

Create this table manually in the Catalyst Development Data Store before
calling the probe. Catalyst SDK row insertion does not create tables or
columns.

Table name: `MigrationProbe`

| Column | Type | Maximum length | Mandatory | Unique | Default |
| --- | --- | --- | --- | --- | --- |
| `probe_value` | Text | 10,000 characters | Yes | No | None |
| `probe_marker` | Text | 10,000 characters | Yes | No | None |

Catalyst creates `ROWID`, `CREATORID`, `CREATEDTIME`, and `MODIFIEDTIME`
automatically. Do not add or modify those columns. Text columns do not support
default values in Catalyst Data Store.

Do not insert customer, credential, token, or production business data.

## AppSail Probe

The existing API exposes `GET /health/catalyst`. It uses the native
`zcatalyst_sdk.initialize()` lifecycle, obtains Data Store and ZCQL services,
and runs:

```sql
SELECT ROWID FROM MigrationProbe LIMIT 1
```

The endpoint returns only a status and dependency name. SDK exceptions are
normalized and their messages are never returned.

## Disposable CRUD Endpoint

Set `CATALYST_PROBE_CRUD_ENABLED=true` only for the Development connectivity
test. Then call `POST /health/catalyst/crud` from the deployed AppSail API.
The endpoint generates a disposable marker internally, performs insert,
select, update, delete, and cleanup, and returns only `PASS`/`FAIL` values.
It is disabled by default and must not be enabled in Production.

## CRUD Proof

The next Development-only probe should use the adapter methods against the
same table and disposable values:

1. Insert a row and capture the returned `ROWID`.
2. Select it with ZCQL using a trusted, fixed query.
3. Update it by passing the returned `ROWID`.
4. Delete it with `delete_row(ROWID)`.
5. Confirm the row is absent and retain only pass/fail results.

The current repository contains mocked contract coverage for those SDK calls.
Remote AppSail status remains unverified until the current image is deployed
to Catalyst Development and the table exists there.