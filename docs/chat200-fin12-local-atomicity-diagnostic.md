# Chat200 — FIN-12 local ledger/outbox atomicity diagnostic (DRAFT)

2026-10-31. Inherits Chat199 exact PR #154 HEAD
`620d2dd58fa8a0cfbf2c75e1cda10d2e65ca8c1f`,
OPEN/DRAFT/UNMERGED and 9/9 PR CI SUCCESS (backend 8,573 PASS/3 SKIP,
disposable PostgreSQL 15/16: 765 PASS each). All earlier stages preserved.

## Risk assessed
`_write_ledger_entries` explicitly runs in a separate caller transaction
from the main posting operation, whereas the independent `prepare_posting_intent`
stores only an unverified `prepared` outbox. Without a single externally
authenticated provider receipt and proven local commit boundary, a posted
ledger source can coexist with an unconfirmed outbox. An API or AI must never
infer vendor acceptance, run a retry, or auto-delete/rewrite either record.

## Scoped regression-first work
- Unit tests first: `tests/unit/test_chat200_local_atomicity_guard.py`
  (`3e8eda9cce0bce2e903486d9cfe373db3fcff0fe`).
- Disposable PG15/16 test first:
  `test_chat200_posted_ledger_with_prepared_outbox_rollback_is_atomic_locally`
  in `tests/integration/test_chat167_auth_forced_rls_postgres.py`
  (`c2dcffad067d687291886b5dc5d81178d8276788`).
- New `app/api/services/fin12_local_atomicity_guard.py` is a
  **read-only, unregistered** source/intent diagnostic. It requires a
  trusted tenant context and caller-owned DB transaction, recomputes the
  outbox key and stored payload SHA via the Chat199 attestation, verifies
  source identity, and reads existing ledger source links in the same
  transaction. Multiple source links, any posted/orphaned ledger source,
  invalid stored outbox or unverified terminal state fail closed. No writes.
- Synthetic PG test exercises ONE local transaction containing the existing
  ledger writer and outbox producer and confirms that raising the diagnostic
  exception rolls back both. An independent already-committed ledger/source
  anomaly remains untouched for manual investigation; cross-tenant RLS
  prevents another tenant from observing the records.
- CI: explicitly invokes the new unit suite and the existing integration
  suite on disposable PG15 and PG16. No new application route, worker,
  database migration or provider connector was activated.

## Interpretation and remaining external gates
A successful diagnostic with NO ledger source merely means no local posted
ledger was visible to this tenant/session. It does NOT prove transaction
atomicity, comprehensive historic source visibility, provider rejection,
vendor idempotency, a safe retry, or acceptance. A failed check must preserve
historical data and require independent review. The test's single local
transaction is not proof of real ERP+DB atomicity; an external ERP is not in
the PostgreSQL transaction.

**FIN-12 OPEN / EXTERNAL-HOLD:** vendor-authenticated acceptance/status
readback, cryptographic receipt/tenant binding, certified idempotency,
lease/fencing and crash-recovery semantics, single-local-transaction
ledger+outbox+receipt finalization policy, actor JWT/permissions and
Production DB role approval. FIN-11 corrections remain OPEN. No main,
merge, deployment, live DB migration, ERP posting, Windows original edits,
deletion or public GitHub upload of private evidence.

Exact final code/documentation HEAD must pass 9/9 CI; no earlier green SHA
substitutes for final-HEAD verification.
