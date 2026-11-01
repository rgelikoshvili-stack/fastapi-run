# Chat206 — FIN-11 transaction-scoped creator audit lock

Date: 2026-11-01 (Asia/Tbilisi). PR #154 OPEN/DRAFT/UNMERGED.
**Production HOLD.** No live migration, worker, ERP posting, vendor send,
automatic retry, public Maker/Checker route, or source-data mutation.

## Reproduced issue

The *unregistered* `correction_review_service._require_original_maker`
rechecked the source creation `audit_log` event during independent checker
approval (Chat205), but read that event with an ordinary SELECT. Under
PostgreSQL READ COMMITTED a concurrent writer could UPDATE or DELETE the
verified audit event **after** this read and before the review transaction
committed. This undermined the temporal stability of review evidence.
This is a synthetic reproduction, not proof of a production attack.

## RED-first GitHub evidence

- `493fd55f7a3b9772c5942e448008502cc73d06b2`: add
  `tests/unit/test_chat206_fin11_creator_audit_lock.py`. The new case
  requires `ORDER BY id LIMIT 2 FOR SHARE` on the tenant-scoped source
  creator audit query.
- `e1b331d544e40a872fd481df362c4c5766777100`: add one disposable
  SQL regression to
  `tests/integration/test_chat167_auth_forced_rls_postgres.py`.
  A synthetic checker decision is held open while a second PostgreSQL
  connection tries to rewrite the original creation event using a finite
  `lock_timeout=200ms`. Before the fix this UPDATE was not blocked.
- **Measured RED**, exact test SHA `e1b331d...`: backend **1 FAIL /
  8,634 other PASS / 3 SKIP** (run `41244504793`), PostgreSQL 15
  **1 FAIL / 800 other PASS**, PostgreSQL 16 **1 FAIL / 800 other PASS**
  (run `41244504734`). Failure was specifically the newly added
  regression in each suite.

## Scoped repair / GREEN evidence

- Scoped Draft code commit
  `38764d0ca3a5de6f8bb1791e1117265476ded329` modifies **only**
  `app/api/services/correction_review_service.py`:
  `_require_original_maker` uses `SELECT ... ORDER BY id LIMIT 2 FOR SHARE`.
  This locks matching creator evidence rows for the life of the
  caller-owned review DB transaction; a concurrent row UPDATE/DELETE must
  wait or time out. It makes no status transition outside existing inert
  review, performs no ERP posting or release activation, and touches no
  historical audit data.
- **Exact code-SHA CI 9/9 SUCCESS.** Backend **8,635 PASS / 3 SKIP**
  and smoke **1 PASS** (run `41244571226`). Disposable PostgreSQL 15
  **801 PASS**, PostgreSQL 16 **801 PASS** (run `41244571156`).
  The newly added unit and real SQL lock-contention cases PASS.
- Actual frontend dependency install/build steps are **SKIPPED** and
  Cloud Run production deploy job is **SKIPPED**, notwithstanding the
  top-level "Deploy to Cloud Run" workflow reporting SUCCESS.

## Non-negotiable remaining FIN-11/12 gates

- `FOR SHARE` prevents conflicting row UPDATE/DELETE of *matching
  selected events during this transaction*. **It does not prevent new
  phantom/duplicate creation-audit INSERTs**, and cannot certify the
  audit_log is immutable, globally unique or even trustworthy to privileged
  database roles. Reviewed audit GRANT/revoke, append-only DB triggers,
  creation-event uniqueness preflight/candidate DDL, source-lock ordering,
  signed JWT maker/checker actor binding, and independently authorized
  approval states are still OPEN.
- The service is **unregistered**, the Chat192 review DDL is **unapplied**;
  posted ledger reversal/adjustment, financial/report parity and production
  identity checks remain HOLD.
- FIN-12 vendor-authenticated receipt/status and tenant/provider identity,
  certified idempotency, fencing, UNKNOWN outcome reconciliation and a
  reviewed single-local-transaction ledger/outbox/receipt finalizer remain
  **EXTERNAL-HOLD**. Chat201 interlock candidate remains UNAPPLIED.
- FIN-07/08 exact Decimal JSON/UI, indirect cash flow and historical
  statement completeness still OPEN. No main write, merge, Production
  deploy, real migration, ERP dispatch/retry, Windows original-file
  modification, deletion, force push or publication of private evidence.

The final documentation HEAD after this report and Master Plan append must
pass **its own** 9 PR CI checks; do not reuse the code-SHA status.
