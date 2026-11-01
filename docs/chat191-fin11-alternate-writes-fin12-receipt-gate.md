# Chat191 — FIN-11 alternate writer holds; FIN-12 terminal receipt consistency

**Date:** 2026-10-30. **PR #154:** OPEN / DRAFT / UNMERGED. **Production:** HOLD.
**Verified initial checkpoint:** `88c381921edcd3661d45dca247dc631b5754a43e`: exact 9/9 GitHub Actions workflows SUCCESS after Chat190 legacy fixture repairs.
**This stage's code HEAD before documentation:** `747e95bd5faca64213c4b8a758fbf04c83f2382d`. Verify its independent exact-SHA CI before declaring it accepted.

## Scoped FIN-11 changes

- Existing legacy reversal unit-test SQL routing was corrected without relaxing tenant/source classification.
- Added regressions for unsafe edit/delete of terminal or linked drafts, generic/CFO/auto/direct correction approval of linked legacy rows, posted-entry in-place edits, and direct ERP posting of corrections with a forged `approved` status.
- Draft edit/delete/batch correction queries now allow only explicitly ordinary, non-linked, non-terminal drafts. Approval and correction services hold all linked rows, even when legacy `entry_type='normal'`.
- Actual ERP posting preflight now reads `entry_type` and `reversal_of_draft_id` and refuses correction drafts without independently attested maker/checker. This is a safety hold, **not** a completed correction-posting workflow.
- The *unapplied* Chat189 unique-index candidate now rejects ambiguous linked non-adjustment history in its privileged preflight. No historical rows are rewritten.
- A source-congruent disposable database fixture was updated with the existing correction identity columns. No real schema migration.

FIN-11 independent maker/checker identities, complete approval/rejection transition and audit policy, historical inventory, append-only posted-ledger reversal and report parity remain OPEN. The Chat190 same-transaction correction draft/audit gate is preserved, but Production grants and audit immutability remain unverified.

## Scoped FIN-12 changes

The *unregistered and unapplied* `docs/sql/chat186_posting_outbox_DRAFT.sql` candidate now requires a matching immutable append-only accepted/rejected receipt with evidence metadata BEFORE the local intent may become `confirmed` or `rejected`; it also narrows state transitions and protects terminal receipt identity from mutation. Synthetic PostgreSQL 15/16 tests verify refusals and accepted-receipt transition.

This validates a **local consistency prerequisite only**, not actual provider authenticity, lease/dispatch, vendor-certified idempotency, unknown-outcome reconciliation, external-and-local exactly-once behavior, or ledger/receipt atomicity. Existing outbox service remains inert; no connector, task or webhook activated. Real provider schema/roles/credentials and Production release are EXTERNAL-HOLD.

## Controlled evidence

- Baseline starting HEAD: `d2358e763acc5ea14ec626fe9ce5995b4d1274b8`.
- FIN-11 regression-first commits include `dc85cfd3acd49ae194c13edc5641cce6462142cf` and `9429ad1a7820518f058a06e8675aed045e5f6550`.
- FIN-12 regression-first `1a89f594bc011a8d32bd9c180688cf2409d8f48b`.
- Final code candidate `747e95bd5faca64213c4b8a758fbf04c83f2382d`. Its exact CI must be read independently; an earlier green SHA is not sufficient.
- Compare `d2358e7...747e95b`: 17 forward commits, 11 changed/added paths, no deletions reported.
- Actual Cloud Run deploy and frontend source build remain SKIPPED on pull-request CI. No Production, main, live DDL, ERP write, Windows-original edit, merge, force push or private GitHub upload.

Next: complete/review FIN-11 independent maker/checker state machine and immutable reversal; FIN-12 provider-certified receipt, safe UNKNOWN reconciliation, lease/dispatch and single local transaction ledger/outbox record using isolated tests. Do not infer V1 acceptance from these draft foundations.
