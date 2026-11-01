# Chat209 — FIN-11 existing journal correction creator signed-JWT gate

Date: 2026-11-01 (Asia/Tbilisi). **PR #154 OPEN / DRAFT / UNMERGED**.
**Production HOLD**: no merge, main write, release, live DB migration,
ERP posting/retry, vendor send, data deletion or original Windows mutation.

## Confirmed source gap (not proof of production exploitation)

The existing, registered `POST /api/journal-entries/{id}/reverse` and
`/adjust` paths required `approval:write` but derived the audit maker
from `request.state.user_email` or `request.state.user_id`, and the
tenant via legacy `resolve_tenant_id`. That did not invoke Chat208's
signature-verified, live-tenant-member, role/tenant-bound Maker gate.
The resulting creation `audit_log.actor` could therefore differ from
the canonical `auth:<numeric JWT sub>` expected by independent review.
Source-level gap only; no real exploitation or data damage established.

## Regression-first and incremental repairs

- Inherited Chat208 exact SHA
  `f6c000f16b345a6e42bbb86c526a5260a05964aa`: 9/9 CI SUCCESS;
  backend 8,671 PASS/3 SKIP, disposable PG15/16 821 PASS each.
- RED test-only SHA `368a357fc1786ba02d7243689ade98b80887ac6a`:
  `tests/unit/test_chat209_fin11_correction_creation_signed_actor.py`.
  Sixteen new cases for both routes, spoofed user/email/body actor, mismatched
  tenant/role, rejected membership and unavailable identity service.
  **Measured RED** workflow `41304744459`: 16 FAIL,
  8,671 existing PASS / 3 SKIP. Old endpoints did not call the
  attested-maker helper and allowed mocked creation before identity check.
- Scoped first route fix `2f43143abccfe60ded1c5c8fbf62c47143c0ef4f`
  guarded `/reverse`; targeted CI revealed `/adjust` still using
  the old fallback and a legacy pre-auth period override test patch
  referring to a removed resolver (10 FAIL). This intermediate SHA
  **was NOT accepted** as production-ready.
- Independent synthetic *real-cryptographic-signature* acceptance tests
  `9d783af4a23e74f61f4364e301cebfe109d711ce` in
  `tests/unit/test_chat209_fin11_signed_jwt_crypto_acceptance.py`:
  actual HS256 token issuance/verification with TEST-ONLY secret;
  wrong signature, refresh token, missing token, state role/tenant
  mismatch, revoked user and unavailable member service. Actual tenant
  membership query and journal/ERP storage are mocked; no production JWT,
  real database, or external request.
- Follow-up fix `cfd4e14cdbb7e9440e6ae56f4f7ee7aca7422002`
  guards `/adjust` identically. Compatibility test commit
  `40df9ab9c03d795cb678ea0d7683519c41a9a3d6`
  retains the original closed-period override denial while supplying a
  synthetic attested-maker fixture for the now earlier auth boundary.
- Existing routes now call `resolve_signed_review_actor(request, "maker")`
  via a fail-closed helper **before** invoking reversal/adjustment service.
  Only the signed maker's canonical `subject` and `tenant_id` reach
  `create_reversal_draft` / `create_adjustment_draft` and their
  transactionally coupled creation audit. There is no fallback to
  `request.state.user_email`, user body actor or unsigned tenant header.
  Both retain closed-period override denial and ordinary validation.

## Exact code SHA CI — verified

- `40df9ab9c03d795cb678ea0d7683519c41a9a3d6`
  **9/9 PR GitHub workflows SUCCESS**.
- Backend **8,703 PASS / 3 SKIP**, smoke **1 PASS**;
  workflow `41305080623`, job `124843723590`.
  All 32 new Chat209 cases PASS; two old override tests also PASS.
- Disposable PostgreSQL 15 and 16 **821 PASS each**, workflow
  `41305080622`. These PG suites are not a full real signed-JWT to
  financial-ledger E2E test. Role/source/period parity still needs
  isolated integration/staging sign-off.
- The GitHub workflow named "Deploy to Cloud Run" is green, but its
  actual **deploy job was SKIPPED**, as were React dependency install
  and actual frontend Build steps despite a successful frontend-build
  placeholder job. No production rollout.

## Remaining G0-G8 release holds

FIN-11: Only HTTP journal creation is now signed-maker gated **in Draft**;
the low-level callable reversal service still accepts a string actor for
trusted internal callers. Full signed correction creator and Checker
transactions against approved staging real tenant roles, audit owner/GRANT,
Chat192 Maker/Checker and Chat207 immutable/unique creator DDL
(**both UNAPPLIED**), actual immutable posted ledger correction,
status/approval workflow, and financial report parity remain HOLD.

FIN-12: real vendor-certified authenticated receipt/status, tenant-to-vendor
binding, certified idempotency, dispatch lease/fencing, UNKNOWN crash-safe
readback and approved local atomic ledger/outbox/receipt finalizer remain
**EXTERNAL-HOLD**. No provider send or retry. FIN-07/08 exact Decimal
wire/UI/historical and indirect cashflow parity remain OPEN.

All parallel FIN-08 changes and prior history/evidence are preserved.
No merge, main change, production migration/deploy, ERP posting,
Windows original edits, deletion or private Evidence upload.
**Final documentation HEAD must pass its own 9 CI workflows.**
