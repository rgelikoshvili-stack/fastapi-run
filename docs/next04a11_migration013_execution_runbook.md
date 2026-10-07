# NEXT-04A11 Migration 013 Execution Runbook

This document is a readiness artifact, not authorization. Production execution remains
**NO** until every operator-only gate is captured and a separate change authority approves
the exact window, commit, checksum, role, and operator.

## Fixed identifiers

- Application commit: `3d8591784cfd90c40e4681f3ea964bbadf49503f`
- Migration ID: `013_rls_fail_closed_foundation`
- Migration file: `app/storage/migrations/013_rls_fail_closed_foundation.sql`
- SHA-256: `858583ad8c1c4a0c056be10fe998348d302561e9f040f5b3a0915c3e9281860d`
- Lock namespace: `bridge-hub:production:migrations:v1`
- Signed 64-bit advisory key: `-1839300086051708910`
- Protected tables: `counterparties`, `processed_documents`, `journal_drafts`,
  `waybills`, `tax_invoices`, `commercial_invoices`, `triangle_matches`,
  `document_corrections`, `outgoing_invoices`

The lock key is the signed big-endian interpretation of the first eight bytes of
`SHA256("bridge-hub:production:migrations:v1")`. It must not be changed ad hoc.

## One-time control prerequisite

An authorized schema owner, never the runtime role, creates this before the window:

```sql
CREATE TABLE public.bridgehub_migration_history (
    run_id uuid PRIMARY KEY,
    migration_id text NOT NULL,
    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    executor_identity text NOT NULL,
    session_user_name text NOT NULL,
    current_user_name text NOT NULL,
    result text NOT NULL CHECK (result IN ('RUNNING','SUCCESS','FAILED','ABORTED')),
    error text,
    transaction_status text NOT NULL,
    advisory_lock_acquired boolean NOT NULL
);
CREATE UNIQUE INDEX bridgehub_migration_history_one_success
    ON public.bridgehub_migration_history (migration_id)
    WHERE result = 'SUCCESS';
REVOKE ALL ON public.bridgehub_migration_history FROM PUBLIC;
```

Grant only `SELECT, INSERT, UPDATE` on this table to the controlled migration role.
The runner verifies this table exists and never creates it.

## PRECHECK

1. Open an approved change record naming two operators: executor and rollback authority.
2. Recompute the migration SHA-256 and require the fixed value above.
3. Confirm `origin/main`, `/version`, and Cloud Run `COMMIT_SHA` all equal the fixed commit.
4. Confirm `/health` is HTTP 200 and `status=ok`.
5. Confirm the latest deploy workflow succeeded and performed only migration dry-run.
6. Run the read-only runtime-role SQL pack as the exact Cloud Run DB identity.
7. Require NOSUPERUSER, NOBYPASSRLS, no protected ownership, no migration-role membership,
   no schema CREATE, and no policy/ALTER capability.
8. Run the same identity/ownership capture as the controlled migration identity. Require
   NOSUPERUSER/NOBYPASSRLS and ownership of exactly the protected relations needed.
9. Capture `pg_policies`, `relrowsecurity`, `relforcerowsecurity`, relation owners, active
   Cloud Run revision, traffic allocation, and backup/PITR metadata. Do not copy secrets.
10. Verify backup/PITR is enabled and the recovery authority accepts the recovery point.
11. Verify no successful `013_rls_fail_closed_foundation` row exists. If one exists with
    the same checksum, treat the request as a verified no-op; if the checksum differs, STOP.
12. Run the tool without `--execute`; require `mode=DRY_RUN`, the expected checksum, and
    `database_access=false`.

STOP for any SHA mismatch, unknown role, excessive privilege, missing protected table,
missing control table, unverified backup/PITR, unhealthy revision, or unresolved prior run.

## DRAIN

1. Confirm revision `fastapi-run-00480-2n8` or a separately reverified successor contains
   PRs #143, #144, and #145 and serves 100% of traffic.
2. List all revisions and traffic tags. Remove traffic and tags from older revisions only
   under the separately approved execution change.
3. Ensure no rollback automation or tagged URL can send ordinary work to an older revision.
4. Pause/suspend scheduler entry points for autopilot, email polling, learning decay,
   report/export work, OCR callback processing, and other tenant background jobs. Scaling
   alone is insufficient if another scheduler can recreate work.
5. Stop new requests using the approved maintenance mechanism or a revision that rejects
   new business operations while retaining operator health access.
6. Wait at least the maximum request timeout plus the longest background-job timeout.
   Confirm request count, job count, and database sessions from old revisions are zero.
7. Record the drain evidence and timestamp. Keep the application background work paused.

STOP if any old revision retains traffic/tag reachability, work cannot be paused, a tenant
job remains active, or in-flight activity cannot be attributed and drained.

## LOCK

The runner begins an explicit transaction, sets `lock_timeout='5s'` and
`statement_timeout='120s'`, then calls:

```sql
SELECT pg_try_advisory_xact_lock(-1839300086051708910);
```

`false` is an immediate safe stop. The transaction-scoped lock releases on COMMIT,
ROLLBACK, or connection loss. Application replicas cannot run the migration because the
runner is not imported by the application, uses only `MIGRATION_DATABASE_URL`, requires
two operator acknowledgements, and needs the separate owner role.

## MIGRATE

Only after separate production authorization, the controlled job may invoke:

```text
python scripts/run_migration_013_controlled.py --execute \
  --authorization MIGRATION_013_APPROVED \
  --operator-identity <approved-change-and-human-identity>
```

The controlled environment supplies `MIGRATION_DATABASE_URL`; never pass it on the command
line. The runner performs, in one transaction:

1. Recheck the embedded checksum.
2. Set local lock and statement timeouts.
3. Obtain the transaction advisory lock.
4. Verify current/session identity, NOSUPERUSER, NOBYPASSRLS, table ownership, and control table.
5. Reject a successful different checksum; return verified no-op for the same checksum.
6. Insert the RUNNING execution record.
7. Execute migration 013.
8. Verify ENABLE+FORCE RLS and exactly one named policy per protected table.
9. Update the record to SUCCESS/COMMITTED with end timestamp.
10. COMMIT atomically.

Any SQL error, lock timeout, statement timeout, lost connection, or failed verification
must issue ROLLBACK. No policy state or success record may survive a pre-commit failure.
Failure details must be preserved in the controlled job log/change record without secrets.

## VERIFY

Before resuming traffic:

1. Capture the SUCCESS history row and verify migration ID/checksum/executor/timestamps.
2. Re-run the policy, RLS, and ownership portions of the read-only operator pack.
3. Require all nine relations to have ENABLE and FORCE RLS and exactly the expected policy.
4. Using an approved synthetic tenant fixture only, verify tenant A/B isolation, forged
   write rejection, missing/empty/default rejection, transaction reset, and pool reuse.
5. Confirm runtime identity remains NOSUPERUSER, NOBYPASSRLS, non-owner, and unable to alter policies.
6. Check new application logs for RLS errors without exposing tenant records or credentials.

STOP if any catalog result differs, runtime privilege widened, expected policy is missing,
cross-tenant access succeeds, or a tenant-scoped production path fails unexpectedly.

## RESUME

1. Resume one controlled application revision only.
2. Keep background workers paused while `/version`, `/health`, and tenant-scoped synthetic
   reads/writes are checked.
3. Resume background classes one at a time: read-only/reporting first, then email, then
   autopilot/other mutation-capable jobs after log review.
4. Do not resume the legacy default learning-decay invocation until it is made per-tenant
   or explicitly disabled; never restore a default fallback.
5. Observe error rate, DB lock waits, RLS denials, and job failures through the approved window.

## ABORT

Abort before execution for any failed precheck or drain condition. Abort during execution
on advisory-lock failure, lock/statement timeout, checksum mismatch, unexpected role,
missing table, unexpected successful record, SQL error, or verification mismatch. Do not
retry blindly. Preserve evidence, leave background work drained, and obtain a new decision.

## RECOVERY

- Before COMMIT: ROLLBACK is the recovery mechanism; prove catalog state equals the captured baseline.
- After COMMIT: do not recreate fail-open policies, disable FORCE RLS, grant BYPASSRLS, or
  transfer ownership to runtime merely to restore functionality.
- If application incompatibility occurs, keep affected work drained and roll forward a
  tenant-context application fix on a new reviewed revision.
- Use PITR/data restore only if separately authorized and actual data recovery is required;
  policy/catalog incompatibility alone is not permission for data restore.
- The named rollback authority controls any post-commit action. Record revision, traffic,
  policy catalog, migration row, logs, and timestamps before acting.

## Locking assessment

`DROP POLICY`, `CREATE POLICY`, and `ALTER TABLE ... ENABLE/FORCE ROW LEVEL SECURITY`
take strong relation locks; plan for `ACCESS EXCLUSIVE` behavior on each protected table.
All statements are transactional in PostgreSQL 16 and can run in the same transaction.
Active queries can delay acquisition, and held locks block new accesses until COMMIT.
The 5-second lock timeout favors a safe abort over an unbounded outage; 120 seconds caps
the complete statement work. These values must be confirmed by the disposable rehearsal
and may only be changed through reviewed window planning.

## Background-path disposition

- Email poller trigger: every five minutes, after a 30-second startup warm-up. A legacy
  active credential row with tenant ID `default` is enumerated, but `tenant_db_context`
  rejects it before credential retrieval, IMAP, or protected-table access. Valid tenants
  remain independently scoped. The invalid row needs operator cleanup/deactivation under
  a separate data-change approval, not a fallback.
- Learning decay trigger: hourly at application startup. `decay_loop()` calls
  `run_decay_service()` without a tenant, which defaults to `default` and updates only
  `learning_patterns`. That table is outside migration 013, so it does not threaten the
  nine-table RLS transaction, but it is not correctly per-tenant and must remain drained
  until fixed or explicitly disabled.

Because learning decay is a real background data mutation with obsolete default scope,
background readiness is FAIL even though migration 013 itself remains technically isolated.
