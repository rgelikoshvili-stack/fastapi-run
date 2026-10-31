# Chat199 — FIN-12 local outbox idempotency & payload attestation (DRAFT)

2026-10-31. PR #154 OPEN/DRAFT/UNMERGED, no Production/main/merge/real DB/ERP/Windows-original change.
Starting verified PR HEAD `b8ed88fbb72f672bae1e12bdc7d05aaab3116c61`: exact nine GitHub CI workflows SUCCESS. It retains both Chat198 FIN-12 fence-proposal work and independently authored FIN-08 financial statement fixes.

## Risk / why this matters

The unregistered outbox producer `prepare_posting_intent` computed a stable SHA-256 key over `[bridge-erp-intent-v1, tenant_id, journal_draft, source_id, target_system]` and a separate SHA of the canonical payload. However, its conflict readback accepted database columns `idempotency_key` and `payload_sha256` without recomputing them from the persisted `payload_json`, persisted source identity and authenticated tenant. An older direct-SQL row could claim a valid-looking key and payload digest but store different JSONB. The existing DRAFT SQL does not authenticate these fields and the vendor idempotency contract is unknown.

## Regression-first Draft work

- Unit RED commit `081568804314a75881798ddab9ec76e3e2a1270a`: malformed/stale/forged source identity, tenant, target, stored JSONB, hash, UUID and state must be refused, including conflicts that spoof a matching hash.
- Disposable PG15/16 RED commit `da9dbb3177998e85c6e8bb587c96e801ffdf332d`: seed a direct-SQL intent with correct expected hash but a different persisted JSONB; another with bogus idempotency key. Valid producer data must reuse the same id, remain `prepared`, and never create a provider receipt, dispatch or ledger write. Another tenant must not see it under FORCE RLS.
- DRAFT fix `bc971bb532cfb001e222687db7f66a81e4ea558f` in `app/api/services/posting_outbox_intent_service.py`: both INSERT RETURNING and conflict SELECT now retrieve real persisted source identity and JSONB; `_attest_stored_intent` recomputes canonical source key and stored payload SHA, compares it with caller intent, validates source/tenant/target/state/UUID and returns fail-closed error for inconsistent data. Valid canonical JSON with reordered keys is accepted; a legitimately changed payload remains `OUTBOX_INTENT_CONFLICT`.
- Explicit unit/PG15/16 invocation and path trigger in `.github/workflows/chat162-oauth-state-postgres.yml`, commit `dbb4cc6932e73f400c0caa2ca3e0d0d4f300d255`.
- Result ALWAYS has `dispatch_allowed=false`, `retry_allowed=false`, `confirm_allowed=false`, `provider_verified=false`, `vendor_idempotency_certified=false`, `ledger_write_allowed=false`. Local integrity is NOT a vendor guarantee.

## Residual and release restrictions

- This is a read-path/producer-integrity check, not a DB-wide guarantee against privileged direct INSERT, SQL-owner tampering or a separately written future worker. Real provider dispatch is blocked by independent Chat195/196 holds.
- A JSONB codec that changes numeric representation may conservatively reject a historically valid producer payload: operator review/manual correction is safer than suppressing a checksum mismatch. The check cannot certify provider acceptance or replay behavior.
- Certified Balance.ge/1C/Oris idempotency semantics, authenticated receipts/status-query, tenant-to-provider account mapping, crash-fencing/lease with verified provider guarantee, Production JWT/maker-checker roles, safe local ledger/outbox completion and real ERP acceptance remain EXTERNAL-HOLD.
- No production DDL, app route, worker, vendor call, real ledger mutation, main/merge, Windows originals or public upload of private evidence was performed.

**Verification:** require all nine workflows on the exact final HEAD after the documentation commit, including disposable PostgreSQL15 and PostgreSQL16. Green synthetic tests never authorize ERP dispatch.
