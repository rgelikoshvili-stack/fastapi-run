# Posted-Ledger Fixture Verification Results (11C-H16)

## Summary

All 24 fixture verification tests pass. The H15 posted-ledger feature flag and
query builders are confirmed correct against local in-memory fixture data with no
DB connections, no network calls, and no runtime code changes.

## Fixture data

| Header ID   | Tenant          | Status      | In STANDARD_NET? |
|-------------|-----------------|-------------|-----------------|
| hdr-1       | fixture-tenant  | posted      | yes             |
| hdr-2       | fixture-tenant  | correction  | yes             |
| hdr-3       | fixture-tenant  | reversed    | no (excluded)   |
| hdr-draft   | fixture-tenant  | draft       | no (FORBIDDEN)  |
| hdr-other   | other-tenant    | posted      | no (wrong tenant)|

Net headers for `fixture-tenant`: **hdr-1 + hdr-2** (2 entries).

## Verified behaviors

### Feature flag
- `POSTED_LEDGER_REPORTS_ENABLED` defaults `False`; legacy path unchanged.
- When `"1"`, `build_profit_and_loss` returns `data.source == "posted_ledger"`.

### Tenant isolation
- Only 2 net headers returned for `fixture-tenant`; `other-tenant` lines excluded.

### Status filtering
- `reversed` and `draft` headers excluded from net view.
- `posted` and `correction` both present in STANDARD_NET_STATUSES.

### Query contracts

| Report       | Tables                                | Key columns                                |
|--------------|---------------------------------------|--------------------------------------------|
| P&L          | journal_entry_headers, journal_entry_lines | source_draft_id, posting_log_id, evidence_bundle_id |
| Balance Sheet| journal_entry_headers, journal_entry_lines | entry_date ≤ as_of ($3)                    |
| Trial Balance| journal_entry_headers, journal_entry_lines | account_code GROUP BY, SUM debit/credit    |
| Cashflow     | journal_entry_headers, journal_entry_lines | account_code LIKE '1%', cashflow_category  |

No query references `journal_drafts`. `_assert_no_silent_fallback` raises on any
attempt to include it.

### Fail-closed
- DB exception during posted-ledger mode → `ok: false`, `error.code: POSTED_LEDGER_UNAVAILABLE`.
- No silent fallback to legacy path when flag is on.

### Audit / evidence fields
- P&L query selects `source_draft_id`, `posting_log_id`, `evidence_bundle_id`.
- All net fixture headers carry these fields.

### Security
- No secrets (`api_key`, `password`, `token`, etc.) in any query SQL or params.
- No DB/network direct imports (`asyncpg`, `psycopg2`, `requests`, etc.).
- No migration calls or DDL in test file.
- Feature flag not permanently enabled by tests.

### Contract isolation
- H16 imports nothing from `posting_service`, `approval_service`, `posting_helpers`,
  or `approval_patterns` — approval/posting contracts are unchanged.

## Test file

`tests/unit/test_report_service_posted_ledger_fixture_verification.py` — 24 tests,
0 DB connections, runtime: ~0.22 s.

## Run command

```bash
JWT_SECRET=test-secret TEST_MODE=1 DATABASE_URL="" \
  python -m pytest tests/unit/test_report_service_posted_ledger_fixture_verification.py -v
```

Result: **24 passed**.
