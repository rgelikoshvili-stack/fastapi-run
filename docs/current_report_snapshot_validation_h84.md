# H84 — Current Posted-Ledger Report Snapshot Validation

## Scope

This is an opt-in validation pack for the current report-service behavior on the rebased `main` baseline. It is not a production report export, deployment step, or authorization to connect to production. It creates synthetic rows inside a uniquely named temporary schema in a disposable local PostgreSQL database and calls the current `financial_statements_service` builders.

The H53 capture/comparison documents are historical evidence from May 2026. Their approval expired on May 25, 2026; it is not reused or represented as current approval. H84 does not rely on the prior H53 capture output.

## Snapshots captured

For synthetic tenant `h84-tenant-alpha`, period 2026-09-01 through 2026-09-30, the helper captures:

- Trial balance as of 2026-09-30 using `_get_posted_trial_balance_as_of`.
- P&L using `build_profit_and_loss`.
- Balance Sheet as of 2026-09-30 using `build_balance_sheet`.
- Cashflow using `build_cashflow_statement`.

These are actual current service responses, not handwritten SQL approximations. The services identify official Trial Balance, P&L and Balance Sheet values as posted-ledger sourced; cashflow reads posted journal lines and fails closed if unavailable. No draft-based estimates are included or mixed into these official snapshots. A deliberately large draft row and a second tenant are seeded as negative controls; neither may affect tenant alpha's official values.

## Local-only controls

The helper is `scripts/validate_h84_report_snapshots.py` and requires only `H84_REPORT_TEST_DATABASE_URL`. It does not read `DATABASE_URL`, `.env`, application secret storage, or production credentials. Before connecting it requires the exact target `127.0.0.1:55434/bridge_hub_h84_test`. It creates a UUID-named schema, uses synthetic fixture rows only, and drops only that schema on exit. It never prints the DSN or password. The report feature flag is set only in the helper's process and restored afterwards.

Example environment shape (placeholder only):

```powershell
$env:H84_REPORT_TEST_DATABASE_URL = 'postgresql://<test-user>:<local-test-password>@127.0.0.1:55434/bridge_hub_h84_test'
python scripts/validate_h84_report_snapshots.py
```

Do not substitute a production, Cloud SQL, shared, or non-local database. The helper aborts unless host, port, and database name all match the disposable target.

## Snapshot/report contract

- Tenant isolation: every official query receives `h84-tenant-alpha`; tenant beta's synthetic 9,000 GEL row must not appear.
- Posted-ledger source: current service query builders filter headers to `posted`/`correction` and use `journal_entry_headers` + `journal_entry_lines`.
- Draft distinction: `journal_drafts` contains a deliberately conspicuous 888,888 GEL synthetic amount, but it is not a source for these official reports.
- P&L classification uses structured `account_type`; Balance Sheet uses the service's posted-ledger implementation; cashflow uses the PR #127 cash-line classification path.
- The only runtime change is a necessary P&L SQL compatibility fix: PostgreSQL does not support `MAX(UUID)`. Source-draft, posting-log, and evidence IDs are now returned only when all rows in an aggregate share one non-null ID; mixed/partial lineage returns `NULL`. Debit/credit aggregation is unchanged.
- No posted-ledger writer, migration, deploy workflow, production environment, or production feature flag is changed.

## Validation

Unit tests validate the DSN rejection rules, SQL/query-builder contract, tenant/status filters, report response source labels, and absence of silent draft fallback. The `PR 84 Disposable PostgreSQL Report Snapshot` GitHub Actions workflow starts a PostgreSQL 16 service using test-only credentials and a database named `bridge_hub_h84_test`; it runs this helper against that service and runs the existing PR #127 PostgreSQL integration test against the same disposable database. The job does not use repository secrets or production `DATABASE_URL`, and it does not modify the Deploy to Cloud Run workflow. Local execution may be skipped when Docker is unavailable, but the CI job is the required real-PostgreSQL verification path.
