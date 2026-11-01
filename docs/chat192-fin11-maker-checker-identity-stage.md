# Chat192 — FIN-11 maker/checker evidence, Draft-only

**2026-10-30.** PR #154 OPEN/DRAFT/UNMERGED. Production HOLD. No migrations, live ERP writes, main change, merge, deploy, or original Windows edits.

## Scope (no public feature activation)

1. `app/api/services/correction_review_service.py` is **unregistered**. It requires an active trusted tenant-scoped DB transaction and an identity supplied by a separately authenticated call boundary. It cannot run from a public route or AI tool.
2. `docs/sql/chat192_fin11_correction_reviews_DRAFT.sql` is a standalone, unapplied PostgreSQL candidate. Immutable maker/checker review intents and append-only decision evidence have tenant FORCE RLS. No live permissions granted. Direct modification is blocked by triggers and state constraints.
3. The maker must be an authorized accountant/admin and match the exact, earlier `audit_log` correction-creation event's actor, source reference and pending status. Missing, duplicated or conflicting source audit => fail closed. Raw SQL review insertion also runs the creator-source trigger.
4. The distinct checker must have CFO/admin role with `approval:cfo`; same subject (case-insensitive) cannot approve own work. Evidence captures the immutable SHA-256 financial draft fingerprint. A draft changed after submission cannot be approved/rejected.
5. All changes, review events and mandatory audit insertions must occur within the **same caller-owned transaction**. A review decision is **evidence only**: `journal_drafts.status` remains `pending_approval`; the existing posting service continues to refuse correction ERP writes.
6. Reviewer checks require source entry `posted`, original type normal/standard, nonempty reason, balanced lines, open accounting period, tenant lock and authenticated tenant context.

## Verification

Regression-first unit suite `tests/unit/test_chat192_maker_checker.py`; disposable PostgreSQL 15 and 16 `test_chat192_*` cases in `tests/integration/test_chat167_auth_forced_rls_postgres.py`. Both major versions use nonowner FORCE RLS and test 2-person separation, cross-tenant isolation, altered financial content, immutable rejection, direct SQL bypass and no posting. Added explicit unit suite and path triggers to `.github/workflows/chat162-oauth-state-postgres.yml`.

Initial candidate HEAD `92ec7e6adec94efefd31909123ee640d870e0fd9`: 9/9 workflows SUCCESS, backend 8,448 PASS/3 SKIP + 1 smoke, isolated PostgreSQL15/16 630 PASS each. Subsequent maker-origin hardening at `53d2f275d2798202cee50131e4eedb090a0592d4` needs independent exact-SHA CI confirmation.

## Remaining required acceptance (NOT DONE)

- Map JWT session subject to legacy correction creation actor consistently and verify authentication middleware has no unsigned actor or tenant fallback; no public route/permission grant is active.
- Review production `audit_log` append-only constraints and historical duplicate/orphan creation events before migration. An audit table not globally immutable is not independently trusted provenance.
- Add full correction approval/rejection/cancellation and period reopening state machine, journal-draft approved state transition, immutable posted-ledger reversal, currency/report parity and strict ERP receipt synchronization.
- FIN-12 manual provider outcome reconciliation and independently verified provider idempotency remains **EXTERNAL-HOLD**. No `UNKNOWN` automatic retry, dispatch worker, live schema or provider write is authorized.

DO NOT interpret a green synthetic CI as live release readiness. The unregistered service and unapplied DDL intentionally leave the earlier correction posting HOLD in place.
