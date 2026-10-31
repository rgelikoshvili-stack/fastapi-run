# Chat203 / Chat202 continuation — FIN-11 reclassification immutable-source gate

Date: 2026-11-01. GitHub PR #154 OPEN/DRAFT/UNMERGED.
Production HOLD. No live database, ERP or vendor calls.

## Confirmed source defect

The protected regular draft edit/delete and maker/checker paths refused posted
and linked corrections, but `POST /approval/reclassify` selected every
tenant-scoped journal draft with missing/unknown account mapping **without
checking status, entry_type or reversal_of_draft_id**. Its unconditional
`UPDATE journal_drafts` could change accounting classification on already
posted/approved or correction-source rows, outside immutable-ledger review.
A source-level bypass was confirmed; no evidence of live data damage.

## Regression before repair

RED-only commit `4ca562ce5ea93c0aa542f322950509e815e6aeab`:
`tests/unit/test_chat203_fin11_reclassify_gate.py` covers:

1. Read selection excludes posted/terminal and linked correction rows.
2. Conditional UPDATE rechecks approved mutable states and linked identity,
   plus the missing-account predicate, and counts only returned modified rows.
3. A row that becomes immutable after SELECT is not reclassified/count-inflated.

GitHub Actions RED backend run `41239596497`: **3 FAIL, 8,608 PASS,
3 SKIP**. These failures occurred in the new negative regression and
reproduced unguarded source selection, not a vendor I/O event.

## Scoped Draft fix and acceptance

Fix SHA `d39559bc6d984599a1d14adf8d6f093f31f7c833`, limited to
`app/api/routes_approval.py`:
- SELECT and UPDATE require ordinary `entry_type IN ('normal','standard')`,
  `reversal_of_draft_id IS NULL` and draft-only statuses
  `drafted/pending_approval/pending_human_review/needs_correction`.
- UPDATE rechecks the same missing/placeholder-account condition to prevent
  stale read->write races; `RETURNING id` counts actual modified rows.
- No auto-backfill or rewrite of historical posted/terminal/correction rows.
  Legitimate mutable ordinary drafts still reclassify.

Exact fix-SHA GitHub workflow results: **9/9 SUCCESS**.
Backend **8,611 PASS / 3 SKIP**, smoke **1 PASS**, run
`41239692024`; all three new negative cases PASS.
Disposable PostgreSQL 15 and 16: **799 PASS each**, run `41239691861`.
The route regression itself uses isolated SQL-contract mocks; the broader
PostgreSQL CI suite was not a direct browser/E2E verification of this route.
Actual frontend React install/build and Cloud Run deploy job SKIPPED.

## Still OPEN / HOLD

FIN-11: independently JWT-signed Maker/Checker, immutable posted
reversal/adjustment, transaction-local audited reviewer state, secure
attachment evidence mutation paths, period/statement parity and real
role/schema acceptance. FIN-12: real vendor-authenticated receipts/status
and tenant account binding, vendor-certified idempotency, lease/fencing,
UNKNOWN outcome reconciliation, approved local ledger/outbox/receipt atomic
finalizer. Chat201 fail-closed interlock SQL remains UNAPPLIED.
FIN-07/08 exact wire/UI, historical/indirect cashflow completeness OPEN.
No merge, main edit, Production deploy, live migration, external ERP
posting/retry, Windows original edit, deletion or private data GitHub upload.

All previous commits and documentation are retained. The subsequent
documentation-only HEAD must pass its *own* 9/9 workflow checks before
this record is marked final.
