# Bridge Hub Chat187 — FIN-11 posting vs close period concurrency gate

**Date:** 2026-10-30. **PR #154:** OPEN/DRAFT, UNMERGED. **Production:** HOLD.
**Exact green code SHA:** `2c2bc3a5eebf2c221c1b5e0f4518c0c8c2c7f31b`.
Previous Chat180–186 source/plan/report history remains in the same Draft branch.
No main, real Cloud SQL, actual ERP, Windows original, live role, or external money changed.

## Confirmed defects

1. In `posting_service.apply_posting_service`, an exception from
   `period_locks` query was logged but posting continued. A database outage
   could therefore produce a posting in a closed period.
2. The period check and /accounting/periods/lock/unlock were not serialized.
   A close could commit while a posting previously checked an open period.
3. Existing synthetic posting mocks lacked `asyncpg.Connection.is_in_transaction()`,
   and one credentials fixture had a NULL draft accounting date and no explicit
   transaction, so their old assumptions were incompatible with the new safety
   contract. We updated only synthetic test fixtures, not the production guard.

## Change (Draft only)

`app/api/services/period_transaction_gate.py` provides PostgreSQL
transaction-scoped shared year + shared month gates for posting, shared year +
exclusive month gates for month close/reopen, and exclusive year lock for annual
close/reopen. Keys include canonical tenant ID, year and month. Order is always
year before month. Different tenants and unrelated months are not blocked by
a month close. The caller MUST keep the same SQL transaction through period
check, connector dispatch and corresponding local commit.

`app/api/services/posting_service.py` now validates the accounting date and
obtains the posting gate before its period_locks lookup. Missing/invalid dates,
failed SQL, aborted or missing transactions and unavailable lock storage
return `PERIOD_LOCK_UNAVAILABLE` before invoking an ERP connector or performing
a posting mutation. A committed locked period remains `PERIOD_LOCKED`.
`app/api/routes_period_lock.py` uses the matching exclusive close gate for
lock/unlock, and returns a sanitized 503 on storage errors.

## Red-to-green evidence at exact SHA

- Test-only commit `098a2c8b0fb55aa8182b2df04ebb8d17c564ed03`:
  7 expected FAIL on each synthetic PostgreSQL 15/16 (missing gate/module).
- First implementation `35196b88d3a8226de98cea2be7127b34c76f6a33`:
  core period tests green, but legacy mocks and credential fixture exposed
  incompatible synthetic transactions; no safety bypass was introduced.
- `0a5b9688359851a92acd6ccddff64baf345cc051`:
  test fixtures now model real transaction behavior; one leftover
  read-only advisory execute assertion was corrected.
- **Final source `2c2bc3a5eebf2c221c1b5e0f4518c0c8c2c7f31b`: 9/9 GitHub
  Actions workflows SUCCESS**. Backend run 41061053695:
  **8404 PASS / 3 SKIP**, plus separate smoke **1 PASS**.
  Synthetic PG15 & PG16 run 41061053636: **589 PASS each**.
  Vault, Redis, tenant membership, forced RLS, Chroma/ONNX, PR127 reporting,
  PR84 snapshots also PASS. Actual Cloud Run deployment was **SKIPPED**;
  frontend Node install/build **SKIPPED**.

## Limitations / remaining FIN-11 gates

- No full authenticated UI/HTTP real-actor maker/checker E2E was done.
- Legacy reversal/adjustment services call a separate period helper and support
  `allow_closed_period` override; this path is NOT covered by this new
  transaction gate yet. Explicit role/reopen policy and approval required.
- `routes_period_lock.py` still includes runtime CREATE TABLE; production
  DDL/grants/migrations remain OPS-03 EXTERNAL-HOLD.
- FIN-06 append-only candidate conflicts with the historical design of
  updating original header status on reversal. Select and test one safe
  append-only reversal accounting/projection policy before activation.
- While a connector posts synchronously under an open DB transaction,
  the period close waits; FIN-12 durable outbox, provider idempotency,
  timeout/reconciliation and crash recovery are still unimplemented.
- Actual Production tenant/role RLS, PITR/restore, vendor credentials,
  source verification and integration acceptance remain EXTERNAL-HOLD.
