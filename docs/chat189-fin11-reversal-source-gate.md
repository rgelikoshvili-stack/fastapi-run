# Chat189 — FIN-11 tenant-specific reversal uniqueness / concurrency

**Date:** 2026-10-30. **Repository:** `rgelikoshvili-stack/fastapi-run`.
**PR #154:** OPEN, DRAFT, UNMERGED. Production and `main`: HOLD.
**Exact tested code SHA:** `2264a2decf093f0d941413277b87d4be77c9da47`.

## Defect and risk

Before Chat189, `_reversal_already_exists` selected any non-rejected
`journal_drafts` row sharing `reversal_of_draft_id`. Adjustments use
the same reference field, so an adjustment could falsely block the first
real reversal. The check was a cooperative read without a source-scoped
transaction lock and without a database-level active reversal uniqueness
constraint; two parallel requests could both pass and create duplicate
reversal drafts. This is separate from FIN-11's prior period-close gate.

## Draft-only changes

- New `app/api/services/reversal_source_gate.py`: transaction-scoped,
  per-tenant/per-original PostgreSQL exclusive advisory lock. Invalid tenant,
  source ID, absent transaction or unavailable DB lock fail CLOSED.
  `create_reversal_draft` obtains it BEFORE checking duplicates, and keeps
  it through the same transaction's INSERT/COMMIT.
- `_reversal_already_exists` now counts **reversal** entries only
  (`entry_type='reversal'`, status not rejected), not ordinary adjustments.
- New *unregistered* `docs/sql/chat189_reversal_source_unique_DRAFT.sql`
  candidate. Privileged full-history preflight refuses active duplicates and
  missing active reversal identities; appends a partial unique index on
  `(tenant_id,reversal_of_draft_id)` for non-rejected reversals and identity
  CHECK. No automatic history rewriting, dedup, row deletion or backfill.
  This was applied ONLY to disposable PostgreSQL 15/16 test schemas, not
  to a live database, startup migration or Production.
- Corrected real asyncpg INSERT date binding to `datetime.date`, not a
  `str` for a PostgreSQL DATE argument, on reversal and adjustment
  services. Synthetic-only unit mocks were updated, not security disabled.

## Regression and exact CI

1. Red-only commit `65ae5319622ec4b5c6f1d28bbaee750561c58ddd`:
   PG15 and PG16 **7 expected FAIL each / 601 PASS each**, exposing missing
   source lock, missing candidate, false-positive adjustment classification.
2. First implementation `4b7f8914bc3ded815d008348d1b123a8bbd1c27c`:
   PG15 and PG16 **606 PASS / 2 FAIL each**; real PostgreSQL DATE parameter
   mismatch exposed by new integration tests, no Production data involved.
3. Corrected SHA `2264a2decf093f0d941413277b87d4be77c9da47`:
   all **nine** exact-SHA CI workflows **SUCCESS**:
   - Backend **8,420 PASS / 3 SKIP** plus smoke **1 PASS** (run 41068304786).
   - Disposable PostgreSQL 15 and 16 **608 PASS EACH** (run 41068304698).
   - Chroma/ONNX 41068304784, Redis 41068304725, vault 41068304777,
     tenant membership 41068304557, RLS 41068304668,
     PR127 41068304758, PR84 41068304908 all SUCCESS.
   - Actual Cloud Run deployment **SKIPPED**. Frontend Node/setup/build
     **SKIPPED**. Distinct test suites overlap and must not be summed.

Tests include: ordinary adjustment not consuming reversal identity, true
reversal retry, competing concurrent synthetic requests, direct SQL unique
constraint violation, tenant isolation, migration idempotence and dirty
historical preflight refusal. No live ERP/network call was authorized.

## What is NOT complete

**Source-level duplication is DRAFT-VERIFIED only**, not Production protected
until a separately approved reviewed DB migration has passed existing-data
inventory and release checks. Older/ambiguous records with missing
`entry_type`, update/reject transitions, maker/checker segregation,
append-only posted-ledger reversal/correction and transactionally durable
auditing still need independent controls/tests. The existing independent
audit sink is NOT proven atomic with draft INSERT. FIN-12 vendor receipts,
unknown-outcome reconciliation and live provider idempotency remain OPEN.

Any Production RLS/grant/backup/PITR review, staged migration, Windows
original changes, Merge, deploy or live ERP mutation require specific
additional approval. The full private Master Handoff/evidence is never
committed to the public repository.
