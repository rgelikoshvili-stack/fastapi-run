# Indirect cashflow precision — Draft verification

2026-11-01 (Asia/Tbilisi). PR #154 remains OPEN / DRAFT / UNMERGED.

## Confirmed defect
The existing pure `build_cashflow_indirect` helper used binary-float sums for
working-capital, operating and total cashflow adjustments. Individually valid
inputs +1000000000000000, +0.01, -1000000000000000 could produce zero, depending
on grouping or insertion order. Passing an exact database Decimal with the
optional float defaults also raised TypeError. This is a synthetic correctness
reproduction; no production data corruption is asserted.

## Regression first and bounded repair
Test-only `e5aaddb632085fa977373e836f12ca3dd5f4d91e` adds 12 cases and runs
them in the existing isolated matrix. Python 3.11 CI reproduced **10 FAIL**:
backend **8,661 other PASS / 3 SKIP**, PG15/16 **811 other PASS each**.
Two working-capital orders already passed. Python 3.12 local sum is more
accurate and showed 6 FAIL /6 PASS; this difference is recorded, not hidden.

Repair `22cbd6af50cecbb1ff6f8ceb1252fa0a5b3d8974` changes only the indirect
helper and imports the existing report Decimal helpers. Intermediate sums and
report rounding run in their local precision context; the existing JSON number
contract is applied at the final response boundary. Source adjustments are not
mutated. Direct cashflow classification, posting/FX rounding, database schema,
permissions and application routing are unchanged. Local focused verification:
**122 PASS**, including direct cashflow, prior netting and completeness cases.

The new indirect cases are pure arithmetic tests. Their execution in the
PostgreSQL workflow does NOT make them database integration tests. Existing
actual posted writer/report/tenant tests run alongside them. This helper has
no production route/caller discovered in this scoped repository search;
canonical indirect historical data sourcing is still an acceptance task.

## Remaining work
Large final float fields still cannot encode every cent, and a float already
rounded by an upstream caller cannot be reconstructed. Exact-decimal wire/UI,
input-domain/finite-value policy, opening and fiscal-year data completeness,
and direct-versus-indirect reconciliation from authoritative real source data
remain OPEN. This patch does not certify an IAS reporting policy or deployment.
FIN-11 review activation/immutable corrections, FIN-12 authenticated vendor
contracts and all Production acceptance gates remain separate holds.

All prior commits, tests, plans and reports are retained, including concurrent
Chat208 inert actor-verification work. No main/merge/deploy, live migration,
provider send/retry, Windows-original edit, financial deletion or private-file
publication was performed.

## Exact fix-SHA acceptance
All nine workflows succeeded on `22cbd6af50cecbb1ff6f8ceb1252fa0a5b3d8974`.
Backend **8,671 PASS / 3 SKIP**, smoke1 (run 41304067575);
disposable PostgreSQL15/16 **821 PASS each** (41304067586).
Chroma43, Redis210, membership45, vault104, RLS18, reporting270+realDB1,
snapshots82/219+realDB1. Actual frontend Node/install/build and deploy SKIPPED.
This is code-SHA evidence; final documentation HEAD is checked independently
and recorded in the private checkpoint. Concurrent Chat208 documentation and
plan commits through `f6c000f16b345a6e42bbb86c526a5260a05964aa` are retained.
