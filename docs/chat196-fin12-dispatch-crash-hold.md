# Bridge Hub Chat196 — FIN-12 Dispatch / Crash Recovery HOLD

**Date:** 2026-10-31 (Asia/Tbilisi). **PR:** #154 OPEN/DRAFT/UNMERGED.
**Starting exact HEAD:** `54a3db9c57d08c5033cc746843191e9d74f43cbc`.
**Starting CI:** 9/9 workflows SUCCESS; Backend 8,499 PASS/3 SKIP;
disposable PostgreSQL15/16 685 PASS each. Production and real ERP remain HOLD.

## Reviewed risk

Chat195 had blocked fabricated initial `in_flight`/terminal INSERTs and unverified
`confirmed`/`rejected` outcomes. However the unapplied Chat186 outbox DDL
still allowed an arbitrary UPDATE from `prepared` to `in_flight` before a
verified vendor idempotency, dispatch lease or provider-authentication contract
existed. A direct SQL state change could masquerade as a sent ERP request.
The existing `updated_at` is not a trustworthy lease expiry timestamp;
neither a crash nor elapsed wall time establishes the vendor's commit outcome.

## Chat196 red-first changes (Draft only)

1. Regression tests were committed BEFORE remediation:
   - `tests/unit/test_chat196_dispatch_crash_hold.py`: every classification
     denies dispatch/retry/confirm/ledger mutation, invalid or missing
     tenant+actor/transaction are rejected; unknown emits a manual hold.
   - `tests/integration/test_chat167_auth_forced_rls_postgres.py`:
     non-owner disposable PG15 and PG16 direct SQL UPDATE to
     `in_flight` must be refused, tenant visibility and immutable HOLD
     records are checked, no real receipts or ERP mutation occur.
2. `docs/sql/chat186_posting_outbox_DRAFT.sql` now rejects *any* new
   `in_flight` transition until an externally certified dispatch
   contract is reviewed (`FIN12_DISPATCH_CONTRACT_UNVERIFIED`).
   The prior `unknown -> in_flight` and fake confirmation holds remain.
3. **Unregistered** `app/api/services/posting_outbox_crash_hold_service.py`
   records an immutable manual quarantine observation for a source
   **already `in_flight` or `unknown`**. It checks tenant context,
   caller-owned transaction, source/target/identity hash consistency,
   minimal role shape and an explicit observation reason. All outputs return
   `dispatch_allowed=false`, `retry_allowed=false`,
   `confirm_allowed=false`, `ledger_write_allowed=false`,
   `provider_verified=false`.
4. **Unapplied** `docs/sql/chat196_fin12_crash_hold_DRAFT.sql` defines a
   per-intent immutable audit-only HOLD row (one per tenant and outbox),
   FORCE RLS, strict source-state trigger, no live grants and no mutations
   to the original intent/ledger/provider. No network, vendor callback,
   launch job or posting API was registered.
5. `.github/workflows/chat162-oauth-state-postgres.yml` now invokes
   the Chat196 unit tests and runs all appended integration scenarios in
   both PostgreSQL 15 and 16, isolated synthetic credentials only.

## Still not complete / external acceptance

Vendor-certified idempotency and replay semantics, reliable authenticated
provider status readback/receipts, dispatch lease ownership/fencing,
monotonic lease epochs and clock trusted by DB, crash-after-send recovery
without duplicate ERP posting, independent exact-once local ledger/outbox
completion, verified JWT actor binding, live DB role/DDL review and balance
report parity are **OPEN / EXTERNAL-HOLD**.

This step is deliberately a **quarantine-only recovery stage**, NOT a
working dispatcher or automatic `in_flight -> unknown` transition.
No safe attempt to re-send can be authorized from these records alone.
The signed synthetic receipts of Chat194 and manual claims of Chat193
are not real Balance.ge/1C/Oris authenticated outcomes.

**Controls:** no main change, Merge, Production Deployment, real DB migration,
real ERP posting, Windows original editing, data deletion or private evidence
upload to public GitHub. Verify this stage's exact final HEAD and all nine CI
results separately before documenting it as Draft-tested.
