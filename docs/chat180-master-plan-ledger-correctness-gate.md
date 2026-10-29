# Chat180 — Master completion plan and posted-ledger correctness

Date: 2026-10-29. Existing Draft PR #154 only. Production HOLD.
Baseline: `52a35d9b8330bbbf9aa6b91c17f01cf9f4ce7b46`.
Planning commit: `c215adb8073babfe6c2c44d155df4ff66a8eae54`.

## Stage 0: one project completion plan

`docs/MASTER_COMPLETION_PLAN.md` consolidates 54 feature/work items, V1 vs
later scope, P0/P1/P2 order, review-slice dependencies and G0–G8 acceptance.
It preserves all older plans and distinguishes implemented code, executable
evidence, remaining repair, completion, retest and external approval gates.
Both Draft PRs and main were rechecked: #154 already contains #153.

The baseline inventory hashes all 1,054 tracked files and parses all 738
Python files without syntax errors; 358 app Python files, 276 unit and 65
integration test modules, 168 docs, 36 static HTML and 575 declared route
decorators. Declared routes are not necessarily registered/live endpoints.
This is source inventory and focused review, not line-by-line whole-repository
security certification. Existing subscription middleware/service are registered;
older planning text claiming they are absent is stale. Seven independently
deployed AI agents and a durable Central Bridge bus are not established by
the existing wrapper/module names.

## Stage 1: confirmed ledger data defects

The actual writer used permissive `_to_decimal` conversion (invalid text
becomes zero), summed raw amounts for headers but rounded individual lines,
silently skipped missing accounts, and converted NUMERIC values to binary
floats. A balanced raw journal could therefore persist header totals different
from its rounded lines; large exact amounts could lose cents. Missing source
IDs/dates and a mismatched draft tenant were not rejected at this boundary.
Foreign-currency recovery with an empty payload could silently use rate 1.

New pure `posted_ledger_validation.py` validates every line and exact stored
cents, rejects malformed/nonfinite/negative/both-sided/empty/unbalanced data
and numeric overflow, preserves the caller's draft, and never invents a
balancing line. `posting_service.py` validates canonical tenant/source/date,
requires explicit FX for non-GEL postings, prepares all amounts before INSERT
and passes Decimal values directly to PostgreSQL NUMERICs. Sequential source
retry remains a no-op. Foreign-currency recovery without the original verified
posting FX now fails closed; restoring the original FX provenance is a tracked
follow-up, not silently replaced by today's rate.

The separate trial-balance query in `ledger_service.py` still joined lines
by header ID alone and passed ISO strings into asyncpg DATE parameters. It now
joins both tenant and header and reuses `_pg_date`. The existing broad-line-RLS
adversarial real-DB fixture now also invokes the actual routed trial service
with a bounded date range. It must agree with P&L/AI and exclude the injected
other-tenant line under both broad and strict synthetic line policies.

## Tests and compatibility

- New writer regression: 18 failed before the fix.
- Initial focused regression: 113 passed after the fix.
- Real disposable PG15/16 tests add invalid-data/no-rows behavior, rounded
  cent equality between headers and lines, large exact Decimal persistence,
  and other-tenant absence. Migration 011 only in isolated test schemas.
- Earlier mock-only fixtures used single unbalanced debit lines or expected
  an empty source to succeed; those fixtures now model balanced journals and
  migration-011-compatible sources. No application guard was weakened.
- No new production migration, configuration/flag activation, cloud resource,
  live ERP/provider call or Windows original write. Existing source files,
  commits and historical reports retained.
- Exact stage-1 implementation `af537f8917864120d347c87fcb1a6ef71dd52408`: all 9 workflows PASS. Backend 8,276 PASS / 3 SKIP plus smoke 1 (40918165408); PG15/16 432 PASS each (40918165452); Chroma/ONNX 43 (40918165736); Redis 210 (40918165245); membership 45 (40918165359); vault 104 (40918165609); finance RLS 18 (40918165336); PR127 229 plus smoke 1 (40918165345); PR84 82/178 plus smoke 1 (40918165606). Actual deploy and frontend build SKIPPED. Final focused local suite 114 PASS; local full suite before the extra micro-credit case 8,275 PASS / 3 SKIP.

## Stage 2: cooperating ledger writers and transaction lifetime

A synthetic scheduled execution of the actual stage-1 writer reproduced two
headers/source rows from two callers for the same tenant/draft. The pre-check
was not sufficient to serialize concurrent attempts.

The writer now requires an actual transaction and acquires a transaction-level
PostgreSQL advisory lock on a stable JSON namespace/tenant/draft key before
checking the source. The lock lasts through commit/rollback. The source check
explicitly requires READ COMMITTED; an earlier repeatable-read snapshot could
otherwise miss the preceding writer's commit even after waiting for the lock.
Unsupported isolation fails before INSERT; the code does not change the caller's
isolation or active database configuration. Existing valid retries remain no-ops.

New disposable PG15/16 tests start eight simultaneous connections across two
tenants with the same draft ID, require one header/two lines/one source per
tenant, verify full caller rollback and successful retry, reject autocommit,
and reject repeatable-read/serializable without rows. This is cooperative
application idempotency, not a unique constraint against arbitrary SQL writers
and not a guarantee that the external ERP receives a transaction only once.
Stage-2 exact-SHA CI pending.

## Remaining work

Arbitrary direct SQL still needs a reviewed source uniqueness invariant.
Historical/custom account classification,
complete non-GEL report conversion, balance retained-earnings reconciliation,
unknown cashflow disclosure, immutable ledger constraints and all live
RLS/backup/provider/UI gates remain explicitly open in the master plan.
