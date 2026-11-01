# Chat197 — FIN-12 UNKNOWN receipt trust boundary (Draft-only)

**2026-10-31.** PR #154 OPEN / DRAFT / UNMERGED. No main change, merge, live
database migration, Production deployment, real ERP write, worker activation,
Windows original edit or public private-evidence upload.

## Verified handoff

Inherited Chat196 HEAD: `1d3793b4ff25b8e6dcb0b9f2fe8030d35e13eb1d`,
all 9 GitHub PR workflow runs **SUCCESS** (Backend 8,517 PASS / 3 SKIP,
disposable PG15 and PG16 704 PASS each; Cloud Run deploy job SKIPPED).
All earlier code, tests, plans and evidence preserved.

## Security issue (FIN-12)

The standalone, UNAPPLIED `docs/sql/chat186_posting_outbox_DRAFT.sql` correctly
refused inserts of unverified `accepted` and `rejected` provider receipts.
However, the same provider receipt table still allowed `outcome='unknown'`
with forged `provider_receipt_id`, `verified_by` and `verified_at`
metadata, or a bare unknown receipt attached to a still-`prepared` intent.
Such rows are NOT signed vendor proof but could later be misinterpreted as
provider evidence. Chat193 manual reconciliation and Chat196 immutable crash
HOLD records already provide safer places to store uncertainty.

## Regression-first Draft fix

1. Commit `19ef971983d59b18a1eb704b03c9db0decfe436a` added a synthetic
   PostgreSQL 15/16 regression covering:
   - forged / blank `unknown` receipt evidence for prepared/unknown sources,
   - cross-tenant receipt insertion attempt,
   - zero persisted provider receipts and unchanged source states.
2. Updated only the standalone, unapplied Chat186 outbox DDL:
   `fin12_hold_unverified_provider_receipt` now **rejects UNKNOWN too** with
   `FIN12_UNKNOWN_PROVIDER_RECEIPT_HOLD`. Existing `accepted`/`rejected`
   hold (`FIN12_UNVERIFIED_PROVIDER_RECEIPT_HOLD`) is unchanged.
   All three provider receipt outcomes remain unavailable without a separately
   validated real provider authentication protocol.
3. Existing composite `(outbox_id,tenant_id)` FK and FORCE RLS continue to
   enforce source isolation as defense in depth. No trigger SELECT is used:
   unbound privileged test sessions must not convert a valid HOLD decision
   into a misleading RLS-filtered source-not-found result.
4. Updated the old Chat186 synthetic cross-tenant assertion to expect the
   stronger unconditional `unknown` receipt HOLD, before any real provider
   records can be written. No historical test is removed.
5. The immutable, unregistered Chat193/Chat196 manual HOLD services remain
   the only Draft models for unverified operator claims/crash ambiguity.
   Their results never grant `dispatch`, `retry`, `confirm` or ledger writes.

## Still OPEN / external requirements

- Actual provider-approved receipt format, trust anchors/key rotation and
  independently authenticated vendor status readback.
- Real vendor-certified idempotency, dispatcher lease ownership/fencing,
  crash-after-send outcome reconciliation without blind replay.
- Verified JWT actor binding, provider tenant/account binding, local
  ledger/receipt/outbox one-transaction completion, history and report parity.
- Approved live migrations/grants and Production deployment after separate
  explicit user authorization.

**Evidence:** exact final post-documentation SHA and all nine CI workflow
results must be verified independently. A green disposable test is not a
real ERP receipt contract. This is strictly a fail-closed Draft-only fix.
