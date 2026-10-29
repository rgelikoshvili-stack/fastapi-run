# Chat180 — Master completion plan and finance/tenant correctness

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
Stage-2 exact implementation `a91b50f60281600edc8c8d4a79f925e9369384ad`: all 9 CI workflows PASS. Backend 8,277 PASS / 3 SKIP plus smoke 1 (40920074538); PG15/16 437 EACH (40920074738); Chroma/ONNX 43 (40920074824); Redis 210 (40920074815); membership 45 (40920074648); vault 104 (40920074668); finance RLS 18 (40920074887); PR127 229 plus smoke 1 (40920074610); PR84 82/178 plus smoke 1 (40920074601). Actual deployment and frontend build SKIPPED. Local focused concurrency suite 88 PASS.

## Stage 3: ERP learning-memory authority and permissions

Confirmed routes omitted tenant propagation and fell back to shared `default`
rows. The upsert route accepted `posting:read`. The connector factory ignored
`mode=demo`; 1C could load global credentials. Generic live Balance history
projects `erp_id/date/amount/description/status`, dropping source identity and
account fields required by memory upsert; ORIS has no history adapter.

All four routes now use the existing signed-tenant permission guard; upsert
requires `posting:write`, GET list keeps `posting:read`. Services require the
current authorized DB tenant before opening a connection or connector, and
reject explicit mismatches/default. Body tenant hints are never authority.
Optional classifier enrichment returns no ERP match if scope is absent or
inconsistent. SQL operations always close/return connections, including errors.
Per-row and route failures no longer echo raw SQL/exception text or raw financial
rows; incomplete imports return outer `ok=false` with retained safe counts.

Demo history is an empty, explicitly simulated, non-authoritative preview and
never persists evidence or loads provider credentials. Generic live history
fails closed with `ERP_HISTORY_LIVE_ADAPTER_UNVERIFIED` internally and a stable
redacted route error until a tenant-bound source-row adapter is implemented and
reviewed. This deliberately restricts the old incomplete history path; it does
not change other Balance/1C posting routes or activate any feature flag. Signed
JSON history imports remain learning evidence, not official ledger transactions.
Concurrent memory-source deduplication, source revisions and real provider
history remain open in ING-08; legacy/default rows are preserved, not claimed.

New tests: 34 failed / 4 passed before the initial 38-case repair; 49 focused
passed afterwards (38 new plus 11 existing connector tests), then four extra
service/factory guard cases added (final focused suite 53 PASS). Local full suite
before those last four cases: 8,324 PASS / 3 SKIP on Python 3.12; canonical CI
Python 3.11 results must be read independently. Actual nonowner FORCE-RLS PG15/16 test uses
real route/import/list/classifier and sync DB helper against a synthetic schema,
seeds separate A/B/legacy rows, checks zero cross-tenant visibility, refuses
mismatches before connection checkout and returns connections on SQL errors.
Exact stage-3 implementation `da32bac9ce1a8c461f63823adcaec6c5b9e4adb7`: all 9 CI workflows PASS. Backend 8,319 PASS / 3 SKIP plus smoke 1 (40922840715); PG15/16 480 EACH (40922840510); Chroma/ONNX 43 (40922840497); Redis 210 (40922840508); membership 45 (40922840549); vault 104 (40922840821); finance RLS 18 (40922840907); PR127 229 plus smoke 1 (40922840529); PR84 82/178 plus smoke 1 (40922840767). Actual deploy and frontend build SKIPPED.

## Stage 4: incomplete cashflow and unavailable CFO metrics

The pure classifier retained unknown cash movements, but the official response
removed them and published the classified subtotal as complete cash change.
The CFO aggregator turned missing cashflow into zero. A synthetic row with
unknown account metadata reproduced an omitted movement; 12 new cases failed
before the change.

An official period with any unknown movement now returns
`CASHFLOW_CLASSIFICATION_INCOMPLETE` and only a safe movement count/period,
without fabricated classifications, raw financial rows or a partial official
total. Fully classified periods return `complete=true` and `source=posted_ledger`.
CFO metrics distinguish cash balance availability from cashflow availability;
missing, partial, malformed or nonfinite cashflow yields null metrics and
`cashflow_available=false`. A verified complete zero remains zero. This is an
intentional response-contract correction; frontend empty/error-state acceptance
remains in UI-01/02 and is not inferred from backend tests.

Local focused suite: 160 PASS, including the new 12 cases. The existing real
PostgreSQL fixture deliberately contains one unclassifiable movement: it now
requires unavailable unbounded official cashflow, a successful bounded known
period, tenant-B isolation, and an available trial cash balance alongside null
cashflow KPIs. Actual classification guesses and historical financial rows
are not changed. Exact stage-4 CI pending.

## Remaining work

Arbitrary direct SQL still needs a reviewed source uniqueness invariant.
Historical/custom account classification,
complete non-GEL report conversion, balance retained-earnings reconciliation,
complete unknown-cashflow review workflow, immutable ledger constraints and all live
RLS/backup/provider/UI gates remain explicitly open in the master plan.
