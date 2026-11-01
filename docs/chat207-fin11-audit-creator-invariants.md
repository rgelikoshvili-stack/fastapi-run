# Chat207 — FIN-11 creator audit uniqueness and immutability candidate

Date: 2026-11-01 (Asia/Tbilisi). GitHub PR #154 **OPEN / DRAFT / UNMERGED**.
**Production HOLD.** No live database migration, registered runtime route,
ERP posting, vendor dispatch/retry, data correction, history rewrite or deletion.

## Confirmed source gap

Chat206 added `SELECT ... FOR SHARE` for selected maker creation audit rows
during the unregistered independent checker transaction. This did **not**
block a concurrent *new* audit INSERT for the same correction draft, nor
prevent UPDATE/DELETE outside that short transaction. The source audit
table had no demonstrated unique correction-creation identity and no
append-only DB trigger for those creator actions. Tests reproduce the
absence of that control in a **disposable** database only.

## Regression-first observed (RED)

`576a4fd4f6f2b25e981a996e56a8c3af102ca46e` appended isolated
PostgreSQL tests to
`tests/integration/test_chat167_auth_forced_rls_postgres.py`. Before
the candidate DDL was present, each major version reported **4 FAIL /
802 other PASS** (GitHub run `41245291949`): the DB accepted
two same-action/cross-type creator events for one tenant/draft, and
allowed UPDATE and DELETE of source audit evidence.
The unrelated-event and other-tenant independence case already passed.
No live audit rows were touched.

## Scoped Draft-only candidate and acceptance

- Candidate-only `docs/sql/chat207_fin11_creator_audit_guard_DRAFT.sql`
  committed at `4ec39d7a75d698a76f9cbaa5ff03b540f61c70f8`.
  **Not in app/storage/migrations; not invoked by runtime.**
- Mandatory historical duplicate/invalid-identity PREFLIGHT refuses
  applying the candidate; it never auto-repairs or deletes source rows.
- Partial unique index on `audit_log(tenant_id, resource_id)` for
  `journal_drafts` creator events, covering BOTH
  `reversal_draft_created` and `adjustment_draft_created`.
  Unlike a row-level SHARE lock it prevents competing duplicate inserts.
- Scoped audit trigger refuses UPDATE/DELETE of protected creator rows,
  including relabeling them out of the protected class, and refuses an
  UPDATE relabeling an unrelated row into a protected creator event.
  Invalid/null resource identifiers are rejected for new creator INSERTs.
  Unrelated audit actions and other tenant identities remain unaffected.
- Repeated execution in disposable PG15/16 test schema is idempotent;
  no runtime GRANT or live migration is provided.
- Exact candidate SHA `4ec39d...`: **9/9 GitHub CI SUCCESS**,
  PostgreSQL 15 and 16 **806 PASS each** (run `41245504831`).
- Additional acceptance tests at
  `620aba5b58d8c94b42446d22ae28e6c0d8812657` prove duplicate
  historical preflight without deletion, invalid/new identity denial,
  unrelated-event relabel denial, and tenant-scoped nonowner direct
  SQL duplicate rejection. Exact SHA: **9/9 PR workflows SUCCESS**;
  Backend **8,635 PASS / 3 SKIP**, smoke **1 PASS**
  (run `41245693517`), disposable PG15/PG16 **809 PASS each**
  (run `41245693524`). The Cloud Run deployment job and actual
  frontend dependency installation/build are **SKIPPED** in PR.

## Mandatory release holds / limitations

1. This is **unapplied candidate SQL**, not proof of real audit grants,
   historical data cleanliness, a migration rollback procedure, or
   nonowner production runtime acceptance. The synthetic schema does
   not certify production. A privileged owner can disable triggers or
   alter tables: operator-reviewed production roles/GRANT/DDL governance
   remain a hard gate.
2. A unique audit key/immutable event does NOT prove the actor subject
   came from a signed JWT or was authorized to create the correction.
   Verified tenant-specific signed identity and creator/role mapping
   still HOLD. The isolated review service stays unregistered; Chat192
   review DDL and this Chat207 DDL stay unapplied.
3. Immutable posted-ledger reversal and true financial statement parity
   remain FIN-11 OPEN. Source lock-ordering and concurrent
   historical-inventory/release acceptance are not yet certified.
4. FIN-12 provider-signed receipt/status, tenant-to-provider account
   binding, vendor-certified idempotency, lease/fencing, crash UNKNOWN
   reconciliation, and safe single-local-transaction ledger/outbox/
   receipt finalizer remain **EXTERNAL-HOLD**. No vendor send/retry.
   FIN-07/08 exact Decimal wire/UI and indirect historical statements OPEN.
5. No Merge, `main`, Production deploy, live migration, ERP posting,
   original Windows file mutation, deletion, forced history rewrite, or
   public upload of private Master Handoff/Evidence ZIP is authorized.

**The final documentation HEAD needs its own 9/9 CI verification**;
the green code SHA cannot be used to certify a later documentation SHA.
