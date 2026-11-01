# Chat190 — FIN-11 source classification, approval hold, atomic draft audit

Date: 2026-10-30. PR #154 OPEN / DRAFT / UNMERGED. Production HOLD.

## Exact prior checkpoint

Chat189 documentation HEAD `91d9dfddc42b07bc2d425989b195fd383cb38491` had 9/9 workflows SUCCESS; backend 8,420 PASS/3 SKIP and PG15/16 608 each. This is **prior** verification, not Chat190 final approval.

## Chat190 review findings

1. `_fetch_draft` read status and lines but not the original's `entry_type` or `reversal_of_draft_id`. A posted legacy/linked correction could be treated as an ordinary source.
2. `_reversal_already_exists` ignored unknown or NULL `entry_type` references. Historical ambiguous linked rows can no longer be safely called ordinary adjustments.
3. The correction maker called `log_event()` with an independent synchronous connection. That audit is best-effort and can commit or fail independently of the async draft INSERT.
4. Generic approval, CFO, autopilot, and direct correct-and-approve paths did not attest an independent maker/checker for correction drafts. **No real checker identity/evidence schema was verified**.

## Draft-only remedial controls

- Reversal/adjustment original must have an explicit ordinary `normal` or `standard` type **and no correction source reference**, otherwise `FIN11_SOURCE_CLASSIFICATION_UNVERIFIED`. This may hold historical posted rows until authorized inventory; no implicit backfill.
- Non-rejected correction-linked rows with NULL/unknown type cause `FIN11_AMBIGUOUS_CORRECTION_HISTORY`, not a permissive absence of reversal. A confirmed reversal still consumes its identity.
- Both correction draft INSERT and required `audit_log` INSERT execute on the **same transaction**; audit storage errors cause rollback. This does not certify append-only audit table grants/triggers in Production.
- The generic, CFO, autopilot, and correct-and-approve flows must **not approve reversal/adjustment drafts** without an independently reviewed maker/checker contract. Current behavior is intentionally fail closed / withheld, not a completed approval workflow.
- Existing period-close, source-scoped advisory locks and Chat189 unattached Draft uniqueness SQL are retained. No actual posted-ledger reversal or live DDL.
- Regression tests were committed red-first (`a6d5662584b8c83f646656865115f08ec8f43afc`). Separate remediation commits follow.

## FIN-11 remaining

Independent named maker/checker identities, persistent evidence and approval state machine; all alternate direct-update/batch and API entrypoints; historical reference type/status inventory; mutable rejection identity policy; privileged full-history SQL preflight, append-only actual posted-ledger correction and financial report parity; real PG15/16 and schema/roles verification. All remain **OPEN** until independently tested. No claim of Production readiness.

## FIN-12 next scope

The existing Chat186 `posting_outbox_intent_service.py` and standalone `chat186_posting_outbox_DRAFT.sql` remain inert. Review and isolated test: durable leases, unknown/timeout outcome reconciliation without blind retries, authenticated provider receipts, provider-certified idempotency, and the local ledger/outbox atomic transition. Vendor and real database acceptance: EXTERNAL-HOLD.

No main change, merge, Production deploy, live DB migration, ERP write, Windows-original edit or public private-evidence upload is permitted.
