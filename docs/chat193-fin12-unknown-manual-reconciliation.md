# Chat193 FIN-12 — manual UNKNOWN reconciliation HOLD (Draft)

Date: 2026-10-30. PR #154 OPEN/DRAFT/UNMERGED. Production, actual DB migrations, main and ERP posting: **HOLD**.

## Continuity
Start from Chat192 exact HEAD `51b11db0ad366dd56daf82338938e8175748d509` (9/9 PR CI success; 8,448 backend unit PASS/3 SKIP + 1 smoke; synthetic PG15/16 630 PASS each). All prior work and Master Completion Plan sections retained.

## Findings
- Chat186's durable outbox stores a tenant-scoped immutable intent; its `unknown` result must never authorize a blind retry.
- Chat191's append-only receipt candidate checks *local evidence fields* but does not cryptographically authenticate the real ERP/provider or prove actual vendor idempotency.
- No approved external vendor receipt contract, real ERP dispatch, recovery replay or posting/ledger/outbox atomic transition has been verified. **FIN-12 is NOT complete.**

## Work in Chat193
1. Added `posting_outbox_reconciliation_service.py`, **not registered in any router or worker**, with `open_unknown_reconciliation` and `review_unknown_reconciliation`. Only an authenticated tenant context and caller-owned transaction can read source fields. Runtime outbox access can remain SELECT-only.
2. An accountant/admin may record exactly one operator **claim** (`claimed_accepted`, `claimed_rejected` or `undetermined`) plus a digest of supporting material, never a provider-signed receipt. An independent CFO/admin reviewer can mark **reviewed_hold**, not confirmed or rejected.
3. Both responses explicitly set `dispatch_allowed=false`, `retry_allowed=false`, `confirm_allowed=false`, `ledger_write_allowed=false`, `provider_verified=false`. Source outbox state remains `unknown`; no receipt, financial journal, connector, network request or provider mutation is executed.
4. Separate `docs/sql/chat193_fin12_unknown_reconciliation_DRAFT.sql` introduces an **unapplied** case/event evidence model with strict tenant FORCE-RLS, immutable history, source-consistency insert trigger, independent reviewer and one-way `open -> reviewed_hold` local transition. No Production grants.
5. Regression-first `tests/unit/test_chat193_fin12_unknown_reconciliation.py` and disposable nonowner PG15/16 tests in `tests/integration/test_chat167_auth_forced_rls_postgres.py` cover missing/foreign tenants, absent transaction, forged/invalid claim, duplicate case, self-review, immutable events, direct-SQL prepared-intent bypass and no external outcome confirmation. CI path filters and explicit unit invocation updated.

## Evidence and release blocks
Chat193 tests were committed before implementation. Source evidence: GitHub commits + nine exact-SHA GitHub Actions workflows, to be checked after the documentation update. Earlier green status does not certify subsequent commits.

This is an intentionally **HOLD-only observation module**, not manual clearing of an unknown ERP transaction. Signing/reviewing independent provider receipts, owner/tenant metadata, approved JWT-to-actor binding, vendor-certified idempotency, signed webhook authentication, deduplication, dispatch lease/recovery, ledger/outbox single local transaction, immutable external posting history, actual financial parity and real schema/grants remain **EXTERNAL-HOLD**.

**Do not** automatically retry any UNKNOWN external mutation. Do not promote claimed acceptance to confirmed. Do not trigger real ERP writes or Production deployment. Private handoff/Evidence ZIP are stored outside public GitHub only.
