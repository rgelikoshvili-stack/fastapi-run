# Chat195 FIN-12 — unverified vendor outcomes now fail closed (Draft)

**2026-10-30.** Continues Chat194 exact starting HEAD `05aea2dadb5e1c5ad9f6809b9b98008604b28f19` (9/9 workflow SUCCESS independently rechecked on Chat195 start; backend 8,499 PASS / 3 SKIP + smoke1; synthetic PG15/16 684 PASS each). PR #154 OPEN / DRAFT / UNMERGED. Production HOLD.

## Risk confirmed

The existing Chat186/191 standalone outbox candidate treated a textual `verified_by`, `verified_at`, and SHA digest as sufficient LOCAL evidence for `posting_outbox_intents.state='confirmed'` or `rejected`. This establishes **neither** vendor authenticity nor idempotent delivery. Also, the original `BEFORE UPDATE OR DELETE` trigger did not inspect **initial INSERT**, permitting a direct SQL insertion already marked `unknown` or `confirmed` if other column constraints were met.

Chat194 synthetic test signatures deliberately never authenticate Balance.ge/1C/Oris, so they cannot satisfy a real acceptance gate. No real provider signing/receipt/status API contract was verified.

## Scoped regression-first fix

- Red regression `test_chat195_untrusted_receipts_cannot_create_terminal_intents_or_backfill_acceptance` in disposable nonowner PostgreSQL 15/16 integration suite, committed **before** the fix at `bb412c16b314658265de1f38e472ce0d3b8255d6`.
- Patched only `docs/sql/chat186_posting_outbox_DRAFT.sql` (no registered/live migration):
  1. `BEFORE INSERT OR UPDATE OR DELETE` intent guard refuses all non-`prepared` initial states and initial provider receipt metadata (`FIN12_INITIAL_STATE_NOT_PREPARED`).
  2. A transition to `confirmed` or `rejected` always refuses until an actual provider-authentication contract exists (`FIN12_VENDOR_AUTHENTICATION_NOT_CONFIGURED`), regardless of synthetic receipts.
  3. A separate receipt `BEFORE INSERT` guard refuses `accepted` or `rejected` rows based on local operator-supplied data (`FIN12_UNVERIFIED_PROVIDER_RECEIPT_HOLD`). Unknown outcome observations remain non-authoritative.
  4. The former matching-receipt query remains as **defense-in-depth only**. It is not a vendor authentication proof.
- Adjusted existing Chat191/193/194 disposable fixtures to construct `prepared` intents before exercising `prepared -> unknown`; historical tests and files were preserved, not removed. Earlier Chat191 simulated local receipt confirmation is superseded by the stronger security invariant.
- Repaired explicit PL/pgSQL named dollar-quote tag pairs in the revised DRAFT; final SQL was inspected after commit to confirm the function delimiters balance.

## Still OPEN / external acceptance

No approved real vendor receipt/public-key ownership, tenant-to-vendor account mapping, credential rotation, verified status-readback, provider-certified idempotency, dispatch lease or timeout crash recovery, protected cross-system ledger/outbox atomicity, operator/JWT identity audit, live schema/role review or real ERP acceptance. **Do not** equate green CI, local SQL receipt metadata, synthetic signatures or manual claims with actual provider success.

No public router/worker was activated, no real DB migration, ERP posting, Cloud Run deployment, main edit, merge, Windows original edit or private evidence upload was authorized or performed. This stage's exact final HEAD and 9 workflows must be checked separately from any intermediate green status.
