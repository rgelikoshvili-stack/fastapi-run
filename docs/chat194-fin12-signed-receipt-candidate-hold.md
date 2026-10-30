# Bridge Hub Chat194 — FIN-12 synthetic signed receipt candidate integrity

2026-10-30. PR #154 **OPEN / DRAFT / UNMERGED**. Production, main, real DB/ERP writes, actual vendor calls and Windows originals are **HOLD**.

## Starting checkpoint

Chat193 exact verified HEAD `989861c9db14344a69a67758a68833b8a2124a86` (9/9 PR workflows SUCCESS; backend 8475 PASS/3 SKIP + smoke1; synthetic PG15/16 659 PASS each). All Chat180–193 work preserved.

## Identified trust gap

- The prior standalone Chat186/191 receipt DDL accepts textual `verified_by` and digest fields as LOCAL SQL evidence; these do NOT authenticate Balance.ge, 1C or Oris. The candidate DB state gate therefore cannot be described as proof of actual provider success.
- Earlier Chat193 manual `unknown` reconciliation records unverified operator claims and never clears UNKNOWN. Correct behavior remains HOLD until an independently verified vendor response, provider-certified idempotency semantics and immutable evidence chain exist.
- No trustworthy production provider public key, signature spec, sandbox receipts, callback signing convention, reliable provider query API, key rotation policy, or per-tenant provider account binding was established from the project materials. Do not invent one.

## Chat194 implementation — ALL INERT

1. New `app/api/services/signed_receipt_candidate_service.py` verifies ONLY a **synthetic, domain-separated Ed25519 test envelope**, pinned to a caller-supplied INTERNAL TEST public key, and binds tenant, outbox UUID, source, target, idempotency key and payload SHA-256 to the selected persisted intent. It checks strict UTC timestamp freshness, canonical JSON, signature encoding, signer key ID, receipt identity and status. No secret/private key is committed in application code.
2. Test-only integrity result ALWAYS returns `vendor_authenticated=False`, `provider_verified=False`, `confirm_allowed=False`, `dispatch_allowed=False`, `retry_allowed=False`, `ledger_write_allowed=False`. Even a mathematically valid synthetic signature is NOT a Balance.ge/1C/Oris receipt and cannot clear UNKNOWN or cause a posting.
3. Separate **unregistered/unapplied** `docs/sql/chat194_fin12_signed_receipt_candidates_DRAFT.sql` contains a tenant FORCE-RLS, append-only test candidate table and source-consistency trigger. All records are forcibly `vendor_authenticated=false` and `provider_verified=false`. No live GRANT, no posting-outbox receipt mutation and no ledger state transitions.
4. Regression-first `tests/unit/test_chat194_signed_receipt_candidate.py` and synthetic PostgreSQL15/16 tests in `tests/integration/test_chat167_auth_forced_rls_postgres.py` cover signature tampering, unknown key/rotation, source/tenant/target/idempotency/payload drift, stale/future timestamps, duplicate/replayed candidate, forged SQL against prepared intent, cross-tenant RLS, immutable history and zero ERP side effects.
5. Explicit Chat194 test & path filters added to existing `.github/workflows/chat162-oauth-state-postgres.yml` (the other eight existing workflows retained).

## Remaining FIN-12 external acceptance

Authenticated vendor receipt contract for each actual provider; approved trust anchors and key custody/rotation; independently confirmed callback or signed/status-query trust channel; tenant/company and vendor account binding; lease + crash/timeout reconciliation without blind retries; actual vendor-backed idempotency certification; exactly-once *local* ledger/outbox/receipt transition; financial integrity/report parity; real migration, RLS/grants and sandbox acceptance. FIN-11 posted correction release remains on HOLD.

No production receipt should be automatically equated with a test envelope. A valid synthetic signature does not elevate any real-world assurance. Final exact HEAD and nine CI statuses must be checked independently after this documentation commit.
