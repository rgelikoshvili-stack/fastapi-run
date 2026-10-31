# Chat185 — FIN-06 posted ledger direct-SQL integrity gate

**2026-10-30.** Existing **PR #154 Draft only**, Production **HOLD**.
Exact implementation/test SHA:
`afdf8cc7d20ca8f34005b77160789e07600d2e9c`.
No main write, merge, rebase, Production deploy, Windows originals edit or real data DDL.

## Scope and prerequisites

A cooperative application advisory lock at `a91b50f` was not database
uniqueness against direct SQL. Migration 011 enforced positive individual
values/header debit=credit but did not enforce aggregate stored line totals,
source uniqueness or immutable UPDATE/DELETE. The prior Chat179 DRAFT
candidate adds composite line/header tenant FKs, not complete ledger integrity.

New **standalone, unregistered**
`docs/sql/chat185_posted_ledger_integrity_DRAFT.sql` requires migration011
and both Chat179 composite tenant FKs. It refuses historical duplicate source
keys and incomplete or contradictory header/line/evidence totals before
installation; RLS-off preflight cannot silently pass a filtered subset.
It never modifies/balances/deletes historical rows. It then adds:
- per-tenant unique `journal_draft` and `posting_log` source identity index;
- DB triggers denying UPDATE/DELETE of posted headers, lines and source links;
- deferred, commit-time header/line totals and stored functional currency
  reconciliation, source-existence and matching currency/rate checks;
- repeatable migration application in a disposable schema only.

All testing uses synthetic data. The **actual writer** still inserts a complete
header/lines/source within one transaction; direct SQL attempts to duplicate
the same source, mutate a posted row or commit unbalanced lines fail. Separate
tenants can use the same logical draft ID. Malformed historical fixtures are
retained as-is when the privileged preflight rejects the candidate.

## CI evidence

At the exact implementation SHA, all 9 workflows completed SUCCESS:
backend 8389 PASS / 3 SKIP + smoke 1 (run 41057005185);
PostgreSQL 15/16 570 PASS EACH (run 41057005178);
Redis 41057005024, Chroma/ONNX 41057005132,
membership 41057005160, vault 41057005125, finance RLS 41057005017,
PR127 270PASS + smoke 1 (41057005040),
PR84 82 + 219PASS + smoke 1 (41057005181).
Actual Cloud Run deploy and frontend build remained SKIPPED.
Suites overlap and must never be added into a total test count.

## Remaining boundaries / EXTERNAL-HOLD

No migration is registered or deployed. Current live schema/RLS/grants,
legacy preflight, transactional locks, backup/PITR/restore and backwards
compatibility require independent approved migration scheduling. The SQL does
NOT implement the full FIN11 reversal/correction/close transaction nor the
FIN12 durable ERP receipt/outbox and unknown-response reconciliation.
External provider write idempotency remains UNVERIFIED and disabled.
