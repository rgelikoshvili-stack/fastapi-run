# NEXT-04A11 Production Runtime Role Verification

Status: **PRODUCTION_RUNTIME_ROLE = CANNOT_VERIFY**

No production database query was performed while preparing this pack. An authorized
operator must run `docs/next04a11_runtime_role_operator_checks.sql` using the exact
database identity and connection path used by Cloud Run. Running it as an administrator
does not prove the runtime role.

## Acceptance criteria

The captured output must show:

- `current_user` is the effective application role and `session_user` is the expected login identity.
- `rolsuper=false`, `rolbypassrls=false`, `rolcreaterole=false`, and `rolcreatedb=false`.
- No direct or inherited membership grants superuser, BYPASSRLS, protected-table ownership,
  or a migration/owner role.
- All nine protected tables exist; `relrowsecurity=true` and, after migration 013 only,
  `relforcerowsecurity=true`.
- The runtime role owns none of the nine tables and owns no containing schema.
- The runtime role has no schema `CREATE`, table `TRUNCATE`, or table `TRIGGER` privilege.
- `can_alter_protected_table=false`, `can_create_or_drop_policy=false`, and
  `possesses_protected_table_migration_ddl=false`.
- Before migration, policy output is captured as the recovery baseline. After migration,
  each table has exactly one expected `tenant_fail_closed_<table>` policy.

Any missing row, unexpected inherited role, `NULL` capability, ownership, superuser,
BYPASSRLS, or DDL capability is a STOP condition. Preserve the query output in the
change record without connection strings or credentials; obtain independent review.

## Controlled migration role

Use a distinct, normally `NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`
role such as `bridgehub_migration_013`. A short-lived controlled-job login may be made a
member only for the approved window and must `SET ROLE` before running the tool.

PostgreSQL does not offer a separate `ALTER TABLE` or policy-management grant. The
effective migration role therefore must own the nine protected tables (or use a narrowly
reviewed SECURITY DEFINER mechanism). Required access is limited to:

- `CONNECT` on the target database.
- `USAGE` on the protected schema.
- Ownership of the nine protected tables for `ALTER TABLE` and policy DDL.
- `SELECT`, `INSERT`, and `UPDATE` on `bridgehub_migration_history`.
- No application DML role membership, no superuser, no BYPASSRLS, no role/database creation.

Operator-reviewed template (design only; do not run from this readiness task):

```sql
-- Executed by the existing authorized owner after replacing identifiers.
CREATE ROLE bridgehub_migration_013
  NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE <database_name> TO bridgehub_migration_013;
GRANT USAGE ON SCHEMA <protected_schema> TO bridgehub_migration_013;
GRANT SELECT, INSERT, UPDATE ON TABLE
  <protected_schema>.bridgehub_migration_history TO bridgehub_migration_013;

-- PostgreSQL policy/ALTER authority comes from ownership, not GRANT.
-- Prefer an already-established non-runtime owner. Any transfer of all nine
-- protected tables requires separate review and must never target runtime.
GRANT bridgehub_migration_013 TO <short_lived_job_login>;
-- The job SET ROLEs to bridgehub_migration_013. The runner records both the
-- auditable session_user and the effective current_user.
```

Migration 013 itself needs no schema `CREATE`. Control-table bootstrap is a separate
owner precondition. No application-table DML is granted; ownership inherently supplies
the narrowly held DDL authority needed for `ALTER TABLE` and policy management.

The role must not be placed in the Cloud Run service configuration, frontend, ordinary
application secrets, or startup code. Its credential must be short-lived, auditable, and
available only to the manually approved migration job. Revoke the job login's membership
or credential immediately after the window; do not change table ownership during the
execution window without a separately reviewed ownership plan.

## Control-table prerequisite

Before the window, an authorized owner must create the control table and partial unique
index described in the execution runbook. The ordinary runtime role receives no access.
The controlled runner refuses to create this prerequisite or silently widen privileges.
