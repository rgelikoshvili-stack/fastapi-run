# FIN-08 — unclosed earnings and balance-sheet cutoff (Draft)

2026-10-31. Continues existing PR #154; all prior source and review history
remain. This is an independently reviewable report repair alongside the
Chat198 FIN-12 fencing proposal. Production remains HOLD.

## Problem and resulting behavior

Posted balance sheets selected only asset, liability and equity accounts.
Unclosed income/expense balances therefore disappeared from equity. An actual
disposable PostgreSQL example had GEL 310 cash, GEL 90 booked capital/retained
earnings and GEL 220 unclosed profit, but reported only GEL 90 equity. Legacy
GEL reports had the same omission. The missing-as-of path also displayed
today's date while querying future postings, and treated a one-cent equation
difference as balanced under the old five-cent tolerance.

The same tenant/status/as-of query now includes income and expense balances
from stored functional GEL. Their remaining cumulative credit-minus-debit
balance is presented within equity as `unclosed_result`. Existing closing
entries already transfer those balances to booked equity; fully closed
earnings contribute zero and are not counted again. Losses remain negative.
No period-start or fiscal-year boundary is guessed.

The derived equity line has `line_type="unclosed_result"`, `derived=true` and
`account_code=null`; it is a presentation item, never a new GL account,
retained-earnings journal, database row or balancing plug. Existing booked
equity lines and response totals remain. Zero adds no derived line. A
missing cutoff becomes today's inclusive cutoff in both query and response.
`balanced` now requires equality of the displayed cent-rounded totals.

## Regression-first evidence and review ranges

- Test-only `9f0c96510699d5e665a04904d4270c0d44eb9072` added 14 unit
  cases and the initial real-writer PostgreSQL regression, plus explicit
  disposable CI invocation. PG15/16 each showed **15 FAIL / 705 PASS**,
  including the real `90 != 310` failure, before remediation.
- Implementation `88ac9ef146e2f948eeaad8e80522d661e1f4cb27` changes only
  the financial statements service and adds a second real legacy-GEL test.
  Review `b90c712..88ac9ef`; intervening FIN-12 work and its workflow
  additions are preserved. Local focused tests: 94 PASS; with concurrent
  fencing unit tests: 115 PASS. A pre-reconciliation Python 3.12 whole-unit
  run reported 8,540 PASS / 3 SKIP; canonical counts below are Python 3.11 CI.
- Initial implementation CI had **742 PASS / 1 FAIL per PG version**:
  all FIN-08 regressions passed, while the concurrent FIN-12 fixture's
  no-receipt assertion lacked disposable SELECT permission. Existing
  test-only follow-up `13c2a3b0aea65d6436a7b53bbadf73514cdae769` grants
  that SELECT solely to its ephemeral test role. No production grants changed.

The two actual PG tests exercise the existing writer, mixed USD/GEL stored
amounts, opening capital and retained earnings, explicit/default cutoffs,
future/unapproved exclusion, real closing journals without double counting,
separate tenants, nonowner FORCE RLS and unchanged source rows after reads.
Units also cover loss, zero/partial closing and exposure of a one-cent
imbalance without manufacturing profit to fill the gap.

## Exact implementation acceptance

At `13c2a3b0aea65d6436a7b53bbadf73514cdae769`, all **9/9** PR workflows
are SUCCESS, independently read from run jobs and test log summaries:

| Suite | Result | Run |
|---|---|---|
| Backend / smoke | 8,552 PASS / 3 SKIP; smoke 1 PASS | 41213235394 |
| Disposable PG15 / PG16 | 743 PASS each | 41213235333 |
| Real Chroma / ONNX | 43 PASS | 41213235345 |
| Redis shared quotas | 210 PASS | 41213235338 |
| Tenant membership | 45 PASS | 41213235342 |
| Credential vault | 104 PASS | 41213235411 |
| Finance RLS | 18 PASS | 41213235350 |
| Reporting | 270 PASS plus real-DB 1 | 41213235413 |
| Snapshots | 82 / 219 PASS plus real-DB 1 | 41213235473 |

Actual `deploy` job and React setup/install/build steps are SKIPPED.
The final documentation commit requires its own exact-SHA check; these
results attest the implementation above, not an unknown later branch HEAD.

## Remaining gates and recovery

FIN-08 still needs approved opening-balance and fiscal-year presentation,
multi-year/history completeness, source-specific reconciliation and actual
UI acceptance of the derived line/null account code. Existing JSON numeric
output and other readers' large-value precision are separate open work;
Decimal accumulation here does not certify every report's numeric contract.
FIN-11 immutable correction posting/JWT checker binding and FIN-12 actual
vendor idempotency, receipt/readback, lease fencing and local atomic
ledger/outbox completion remain OPEN / EXTERNAL-HOLD. Unapplied schema
candidates, frontend/browser and live operations gates are not waived.

Recovery is a reviewed Draft revert of the bounded implementation together
with dependent contracts/tests, after checking subsequent changes. No
automatic rollback, release, provider call or historical rewrite is performed.
No main edit, merge, deploy/config change, real DB migration, ERP posting,
Windows-original mutation, data deletion or public private-evidence upload.
