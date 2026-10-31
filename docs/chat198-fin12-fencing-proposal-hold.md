# Chat198 — FIN-12 offline one-shot fencing proposal (DRAFT)

Date: 2026-10-31. GitHub PR #154 OPEN / DRAFT / UNMERGED.
Prior exact accepted Chat197 HEAD: `50223d612e9cec1518da0cf4493edd13372c6f7c`.
Prior 9/9 workflow conclusions SUCCESS; backend 8,517 PASS / 3 SKIP;
synthetic PG15/16 705 PASS each. No Production deployment or real ERP writes.

## Goal and strict boundary

This stage provides an **audit-only one-shot proposal**, NOT a real dispatch
lease or external fencing token. It records a candidate owner/source/idempotency
fingerprint solely for a `prepared` outbox intent in a caller-owned local
transaction. The candidate can never send, retry or confirm a vendor
transaction; hypothetical expiry does not permit reuse.

Without independent Balance.ge/1C/Oris certified idempotency semantics,
real vendor readback, known tenant/provider identity, key custody and
authorized producer/worker lease policy, a real dispatcher MUST remain
disabled. Receipt, UNKNOWN and crash holds from Chats 193–197 stay intact.

## Regression-first code and schema

1. Red-first `tests/unit/test_chat198_fence_proposal.py` covers tenant,
   caller transaction, owner role, invalid/ambiguous source, duplicate owner,
   stale epoch/expiration and permanent fail-closed dispatch/ledger flags.
2. Red-first disposable PG15/16 tests in
   `tests/integration/test_chat167_auth_forced_rls_postgres.py` cover:
   - prepared-only source, exact hash/source/target/tenant binding;
   - direct SQL forged `fence_epoch=2` and wrong source status;
   - unique one-shot proposal per tenant+outbox and no reclaim/retry;
   - nonowner FORCE-RLS visibility, unauthorized cross-tenant attempt;
   - immutable evidence and no provider receipt/outbox state transition.
3. Unregistered `app/api/services/posting_outbox_fence_proposal_service.py`
   records the synthetic proposal from an authenticated tenant context,
   trusted actor/role and caller-owned transaction. Runtime needs **only
   SELECT on the original outbox** and SELECT/INSERT on the candidate
   table in an isolated disposable test, not UPDATE to the outbox.
4. Standalone and UNAPPLIED
   `docs/sql/chat198_fin12_fence_proposals_DRAFT.sql` defines a one-shot
   `posting_outbox_fence_proposals` record with force RLS, composite source
   FK, source integrity/epoch trigger, immutable DELETE/UPDATE guard, unique
   intent and all dispatch/retry/lease/vendor-certified flags constrained FALSE.
   `fence_epoch=1` is a diagnostic proposal only, not an external
   fencing credential. No live grants or scheduled job.
5. Dedicated CI workflow path filters and PG15/16 test command expanded;
   previous workflows/tests/commits retained in the Draft PR.

## Remaining security and functional gates (OPEN / EXTERNAL-HOLD)

- Real producer lease specification, authenticated owner and validated token;
  monotonic lease epochs, proven independent fencing across concurrent workers,
  DB-controlled expiry clock and crash-after-send handoff.
- Vendor-certified idempotency key, provider duplicate response semantics and
  signed/status-readback receipts with tenant account correlation.
- No safe automatic retry from `unknown`, `in_flight` or stale lease expiry.
- Locally atomic verified posting_outbox/receipt/ledger finalization, immutable
  corrections, complete financial statement parity and authorized migrations.
- Independent nonowner Production RLS/roles/DB/ERP acceptance and signoff.
- No publication of PRIVATE handoff/Evidence ZIP on GitHub.

No main change, merge, Production deployment, live DB migration,
ERP posting or Windows original file edits were made. The current stage's
FINAL SHA and 9 CI statuses must be independently checked after documentation
writes; a synthetic green run does not prove real-world vendor delivery.
