# NEXT-04A2 startup DML safety

`run_db_migrations()` is scheduled from application lifespan via
`_run_startup_maintenance()`. It calls `run_index_migrations()` on every
instance startup (unless the existing `SKIP_MIGRATIONS=true` flag is set).
Consequently, startup code must not make tenant-owned business-data changes.

## Removed startup operations

| Operation | Tables | Classification | Reason |
| --- | --- | --- | --- |
| Replace `tenant_id` values that equal `tenants.company_inn` | `journal_drafts`, `processed_documents`, `learning_patterns`, `audit_log`, `bank_transactions`, `chart_of_accounts` | `CANNOT_VERIFY` (historical one-time repair) | The update changes ownership/scope. `company_inn` is not proven unique or an authoritative row-to-tenant mapping; the old tenant value alone cannot authorize the target. No repair is performed automatically or by the application role. |
| Infer missing journal accounts and update draft rows | `journal_drafts` | `OBSOLETE` as startup behavior | Classification is business logic and may alter accounting drafts. It is no longer run during boot; any desired draft classification must use an explicit tenant-authorized workflow. |

No processed-document repair other than the tenant-ID rewrite was found in
startup SQL. Schema/index DDL remains separate and does not select or mutate
tenant rows. Non-tenant exchange-rate metadata backfills are outside this RLS
repair and remain unchanged.

## Controlled historical repair boundary

No repair command is provided for tenant-ID normalization because repository
evidence does not prove a unique authoritative mapping. In particular,
`tenants.company_inn` is indexed but not constrained unique, and `UPDATE ...
FROM tenants` can choose an ambiguous target. This repair is therefore stopped
as `CANNOT_VERIFY`; do not derive mappings from arbitrary business-row data.

If a future audit establishes authoritative mappings, it must be a separately
approved operator-only maintenance tool, never importable/callable by the
request or worker runtime. Before execution it must support dry-run counts
without row contents, reject ambiguous/missing mappings, use a separately
authorized migration role (not superuser/BYPASSRLS application credentials),
run in one transaction under an advisory lock, record a versioned audit result,
and refuse or safely no-op a repeated completed run. A rollback plan must be
based on a pre-approved snapshot/export of affected identifiers and verified
before mutation. None of those prerequisites or an approved mapping source is
currently evidenced, so no executable repair is included here.

Migration 013 remains unapplied to production. This change only ensures normal
application startup no longer performs the cross-tenant DML that would conflict
with fail-closed RLS.
