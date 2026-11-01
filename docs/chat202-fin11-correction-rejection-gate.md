# Chat202 — FIN-11 generic correction rejection must not bypass Maker/Checker

Date: 2026-11-01. PR #154 OPEN/DRAFT/UNMERGED. Production HOLD.

## Confirmed scoped defect

The generic `approval_service.reject_draft_service` checked only ordinary
status before executing an UPDATE to `journal_drafts.status='rejected'`.
Unlike the generic approve and CFO paths, it did not block a correction
(`entry_type = reversal/adjustment`) or any draft with a non-null
`reversal_of_draft_id`. A regular `approval:write` reject (including the
existing batch route's service call) could attempt to bypass the independent
correction review evidence path. This was a source-level authorization gap,
not evidence that an actual production correction was rejected.

## Regression-first evidence

- RED test-only commit: `8c271a80640089159e77b42e08c1231592acafe2`;
  `tests/unit/test_chat202_fin11_correction_rejection.py`, 5 negative cases.
- GitHub Actions RED backend run `41238971704`: **5 FAIL / 8,603 PASS /
  3 SKIP**, failures all in this regression; they observed the path try to
  execute generic rejection SQL and return `REJECT_ERROR` rather than
  mandatory `FIN11_MAKER_CHECKER_NOT_CONFIGURED`.
- Fix: `ff0212b797446a5b3bc0702191ef403625aba695`, scoped solely to
  `app/api/services/approval_service.py` after tenant-scoped
  `SELECT ... FOR UPDATE NOWAIT` and before status/feedback/audit side effects.
  Both explicit reversal/adjustment and any linked legacy/forged normal entry
  now roll back and return `FIN11_MAKER_CHECKER_NOT_CONFIGURED`.
- Exact fix commit GitHub PR CI: **9/9 SUCCESS**; backend **8,608 PASS /
  3 SKIP**, smoke **1 PASS**, disposable PostgreSQL15/16 **799 PASS each**.
  New 5 negative tests PASS. Actual deploy job and frontend build SKIPPED.

This is a constrained, Draft-only application service guard. There was no
real DB migration, production posting, release flag, vendor dispatch, retry,
source rewrite or direct SQL backfill. Existing normal-draft rejection logic
is unchanged.

## Remaining gates

FIN-11: signed JWT maker/checker identity and reviewer transition, durable
transactional audit, posted-ledger immutable correction/reversal, alternate
entry-point inventory and financial report parity are still OPEN.
FIN-12: real vendor-authenticated receipt/status contract, tenant-provider
account binding, provider-certified idempotency, sender lease/fencing,
crash-safe UNKNOWN outcome and a reviewed locally atomic ledger/outbox/receipt
finalizer remain EXTERNAL-HOLD. The Chat201 interlock DDL is UNAPPLIED.
No Merge, main write, Production deploy, live migration/ERP posting, Windows
original mutation, data deletion or private Evidence upload is authorized.
