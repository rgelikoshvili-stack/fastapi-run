# Chat208 — FIN-11 signed Maker/Checker actor gate (INERT)

Date: 2026-11-01. GitHub PR #154 OPEN/DRAFT/UNMERGED.
**Production HOLD**. No public route, live migration, ERP posting,
vendor dispatch/retry, source-data deletion or Production deployment.

## Finding and RED-first evidence

The unregistered correction-review service checks actor/role *strings* but
does not itself verify that they came from a signed JWT and current
tenant membership; its docstring required a future trustworthy caller.
This is a **missing activation boundary**, not evidence of a live exploit.

- RED test commits:
  `ebe4b1fd4723652449b27699f5a748dc5b6a0e62`
  (`tests/unit/test_chat208_fin11_signed_actor_gate.py`)
  and `c8e3eb10fdbf0581429734f0aca8ae8ddcd2d553`
  (`tests/unit/test_chat208_fin11_signed_review_delegation.py`).
- Measured RED at the latter test-only SHA: **24 FAIL,
  8,635 existing PASS / 3 SKIP**, workflow `41303779801`.
  All new failures were missing gate/wrapper symbols, **not** observed
  acceptance of a real forged JWT.

## Scoped Draft implementation and verification

- SHA `3098c35e0ce1bf599122f495e08ac6196320a976`
  modifies only `app/api/services/correction_review_service.py`.
- Adds `resolve_signed_review_actor`, an immutable
  `VerifiedCorrectionActor`, and two **unregistered**
  `submit_attested_correction_review` /
  `decide_attested_correction_review` wrappers.
- Re-verifies Bearer access JWT signature/type using the existing auth
  verifier, checks signed `sub`, role, tenant, email, issued/expiry
  claims, exact middleware identity state and transaction-scoped tenant.
  Rejects duplicate/missing Authorization, wrong tenant, forged role/
  subject, refresh token, malformed claims or insufficient RBAC.
- ALWAYS independently checks current **live tenant membership**
  irrespective of global optional membership flag; revoked membership
  and DB failures deny. Only JWT-bound `auth:<numeric sub>`, role and
  tenant may enter the inert review service. No public API activated.
- **Exact implementation SHA CI 9/9 SUCCESS**; Backend
  **8,659 PASS / 3 SKIP**, smoke 1 PASS (run `41303838661`);
  all **24 new tests PASS**. Disposable PostgreSQL 15 and 16 each
  **809 PASS** (run `41303838659`). Targeted JWT/membership tests
  use mocks; **no real issuer/browser/live membership E2E**.
  Real React install/build and Cloud Run deploy job SKIPPED.

## Shared-branch concurrency and release holds

The shared Draft branch advanced after the implementation code SHA in a
**parallel FIN-08 workstream** (e.g., indirect cashflow decimal tests and
classification logic). Preserve those commits; do not confuse the
implementation-SHA 9/9 result with any later branch HEAD's status.

FIN-11 release blockers: canonical signed JWT subject must also be used
by actual reversal/adjustment creator audit; direct low-level review is
unregistered. Chat192 Maker/Checker and Chat207 audit uniqueness/
immutability SQL candidates remain UNAPPLIED. Production source history,
nonowner roles/RLS, real token/session revocation, approved checker
transitions, immutable posted ledger and report parity still OPEN.
FIN-12 provider-authenticated receipt/status, tenant-provider binding,
certified idempotency, lease/fencing, crash UNKNOWN and atomic ledger/
outbox/receipt finalizer remain EXTERNAL-HOLD. FIN-07/08 exact Decimal
wire/UI and historical/indirect cashflow remain OPEN.

No merge, main write, real migration, ERP posting, Windows original-file
mutation, delete/history reset or private Evidence upload. **Production
HOLD.** Any final documentation HEAD needs its **own** 9 CI checks.
