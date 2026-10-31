# Finance decimal netting and report parity — Draft verification

2026-10-31. PR #154 stays OPEN/DRAFT/UNMERGED. No live activation.

## Confirmed defect and stage 1
Posted and legacy report readers converted stored NUMERIC turnovers to float
before subtraction. For valid stored debit 9007199254740992.01 and credit
9007199254740992.00, P&L, balance sheet, trial balance and CFO cash-position
input could report 0.00 instead of 0.01. Large section totals could similarly
lose a small profit, and a one-cent imbalance could be labelled balanced.

Regression-first commit `c87d25f9c341a444d4154475ca698ad440a84a83`:
13 unit failures plus 2 actual disposable PostgreSQL failures; PG15/16 each
15 FAILED / 775 PASSED. These were assertion failures in the new regressions.
Concurrent Chat200 FIN-12 diagnostic and its workflow changes were preserved.

Repair `c7d13dcf86c459e6f925aef91ee491313e6c6139` keeps Decimal values
through netting, section sums, remaining earnings and balance checks, then
converts at the existing public numeric-response boundary. A local precision
context avoids callers reducing intermediate precision. Legacy source amounts
are accumulated before report rounding. No source row, date/tenant filter,
account classification, booked FX or posting permission is changed.

Exact repair-SHA CI: **9/9 SUCCESS**. Backend **8,595 PASS /3 SKIP** +smoke1;
PostgreSQL15/16 **790 PASS each**. Chroma43, Redis210, membership45,
vault104, RLS18, reporting270+1 and snapshots82/219+1. Actual deploy and
React setup/install/build were SKIPPED. Actual writer -> forced-RLS PG ->
P&L/BS/TB/CFO input and both AI readers retain the small net, isolate tenants
and leave source rows unchanged.

## Stage 2 finding
The direct cashflow reader/classifier/aggregator independently converts
amounts to float before netting. New tests reproduce lost positive/negative
one-cent flows across operating/investing sections and an unequal cash-only
journal misclassified as a neutral internal transfer. Stage 2 is pending
until the separate repair and exact-SHA CI evidence below are recorded.

## Limits and remaining acceptance
Existing JSON number fields remain compatible: very large final numbers are
still floats and cannot represent every cent. A versioned exact-decimal wire
contract and UI/client acceptance remain OPEN; this change certifies internal
arithmetic only. Indirect cashflow/other forecast and account-card readers,
opening/fiscal-year/source completeness and approved historical provenance
need separate acceptance. No production readiness is implied. FIN-11 signed
maker/checker and immutable corrections, and FIN-12 real provider proof and
local finalization, remain OPEN/EXTERNAL-HOLD. No migration, dispatch, retry,
main edit, merge, deployment, Windows-original edit or data deletion.


## Stage 2 Draft repair (after the RED finding; 2026-10-31)

The five prior RED unit cases plus one real PostgreSQL cashflow regression
showed direct cashflow lost a positive/negative GEL0.01 after offsetting
NUMERIC turnovers above 2^53; a one-cent mismatch between two cash accounts
was also marked as an exact internal transfer. Original tests were retained.

Scoped repair commit `2e93f77d89f6a7507eb7e3d2545af4f35bcc62e4` modifies only
`app/api/services/cashflow_classification_service.py`: direct and posted
movements retain Decimal cents until netting is finished, without converting
to binary float during classification/aggregation. Cash-only internal
transfers now require exact equality of booked cents, not a float-derived
0.005 tolerance. Existing public response fields remain floats and the
indirect cashflow path was not modified. No database/ERP write.

This also preserves the concurrent Chat201 FIN-12 interlock and its isolated
regressions, including a test-only RLS SELECT permission correction.
Exact final-HEAD 9-workflow CI remains the acceptance criterion; until it is
confirmed, the stage is DRAFT / pending verification, not production-ready.
The earlier stage-2 'pending' statement records the historical RED finding;
this paragraph records its subsequent repair candidate.
