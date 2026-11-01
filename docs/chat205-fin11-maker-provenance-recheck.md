# Chat205 — FIN-11 Maker/Checker revalidation of creation provenance

2026-11-01 (Asia/Tbilisi). **PR #154 OPEN / DRAFT / UNMERGED. Production HOLD.**
Scope: inert correction-review service only; **no** public route, ERP posting,
signed-identity rollout, database migration, worker, vendor dispatch or retry.

## Defect and why it matters

`submit_correction_review` originally matched the claimed maker against the
source journal-draft creation `audit_log` event. `decide_correction_review`
subsequently relied only on the maker subject copied into the review intent
and the financial draft fingerprint. If the original creation audit evidence
was removed, duplicated, or changed *after* submission, a checker could still
reach the terminal review decision, despite unverified creator provenance.
This is a source-level integrity defect, **not** evidence of real exploitation.

## Regression-first / RED

- `d26210aa4cc9d6389ddcc2abdcab543719b088b1`:
  `tests/unit/test_chat205_fin11_maker_provenance_recheck.py`.
  Six synthetic cases cover missing event, duplicate event, different maker,
  inconsistent source id/status and legitimate unchanged evidence.
  GitHub Actions backend run `41243384617`: **6 FAILED, 8,628 other PASS,
  3 SKIP**.
- `7d5c431d16154aeb23f7409c460c98557f6b14b3`:
  one new, repeatable isolated PostgreSQL test in
  `tests/integration/test_chat167_auth_forced_rls_postgres.py` mutates
  *synthetic test-owner* creation audit after maker submission and verifies
  the checker cannot approve or write a terminal audit/event. The test did
  **not** edit any real database. GitHub disposable PG15/16 run
  `41243516578`: **1 FAILED / 799 other PASS in each version**, specifically
  `test_chat205_checker_refuses_creator_audit_changed_after_maker_submit`.

## Scoped Draft fix and code-SHA verification

- Fix `f5c4718708c585c918c08d4b89bb08c02bfff52e` adds
  `await _require_original_maker(conn, tenant_id, draft, row["maker_subject"])`
  in the independent checker service **after** current fingerprint, source
  link and independent-checker checks, **before** any terminal review event,
  review-state UPDATE or mandatory audit INSERT.
- New tests are unchanged from their RED commits and now PASS.
- Exact fix-SHA CI **9/9 SUCCESS**, backend **8,634 PASS / 3 SKIP**, smoke
  **1 PASS** (workflow `41243540439`); disposable PostgreSQL 15 and 16
  **800 PASS each** (workflow `41243540374`).
- Frontend dependency install / build and Cloud Run production deployment
  remain **SKIPPED** in PR workflow. No live ERP, GCS or production DB access.

## Outstanding explicit holds

This new recheck is necessary but **not sufficient** for Production Maker/
Checker trust. The current creator `audit_log` append-only immutability and
nonowner grants are unverified; provenance could still race with concurrent
modification after a read without a stronger storage-level immutable/locked
evidence protocol. Verified JWT subject-to-creator mapping, auditable
cross-system identity, unique creation evidence, transactional review states,
immutable posted-ledger reversals, financial report parity, and a complete
maker/checker release boundary remain OPEN. The service stays unregistered.

FIN-12 vendor-authenticated receipt/status, provider account binding,
vendor-certified idempotency, lease/fencing and crash UNKNOWN reconciliation,
and one locally atomic ledger/outbox/receipt finalizer remain EXTERNAL-HOLD;
Chat201 local interlock SQL is UNAPPLIED. FIN-07/08 exact wire/UI Decimal
precision and indirect/historical cashflow remain OPEN. Production HOLD.
No merge, main edit, live migration, ERP posting/retry, Windows file mutation,
data deletion, or private evidence on public GitHub.

**Acceptance rule:** this code SHA is green, but the final documentation HEAD
requires its own independent 9/9 checks.
