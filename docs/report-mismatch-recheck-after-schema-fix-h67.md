# Bridge Hub — Report Mismatch Recheck After H66 Schema Fix

**Task:** 11C-H67
**Type:** Authenticated report mismatch recheck — production read-only verification.
**Date:** 2026-05-20
**Branch:** codex/h67-report-mismatch-recheck-after-schema-fix
**Follows:** 11C-H66 `docs/h66-live-verification-closure.md`
**Prior blocker:** 11C-H65B `REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_REPORT_DATA`

---

## 1. Purpose

H67 re-checks the H65B report mismatch finding after H66 schema fixes were deployed.

H65B found that `/reports/trial-balance` and other posted-ledger endpoints returned
graceful `POSTED_LEDGER_UNAVAILABLE` responses because `journal_entry_lines` did not
exist in the production database. H66 added idempotent `CREATE TABLE IF NOT EXISTS`
DDL for `bank_transactions` and `pipeline_runs`, plus `ALTER TABLE … ADD COLUMN IF NOT EXISTS`
statements for `journal_entry_lines.account_type` and `journal_entry_lines.cashflow_category`.

H67 determines whether these fixes resolved the mismatch blocker.

---

## 2. H65B Prior Finding

| Field | Value |
|---|---|
| H65B final decision | `REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_REPORT_DATA` |
| Root cause | `journal_entry_lines` table absent from production DB |
| Posted-ledger migration | Migration 011 created in H4 but never executed against production |
| Behavior | Endpoints returned HTTP 200 with `POSTED_LEDGER_UNAVAILABLE` — no 5xx |
| H65B M6 decision | `TENANT_LEAKAGE_DEEP_CHECK_PASS` |
| H65B M7 decision | `REPORT_MISMATCH_DEEP_CHECK_BLOCKED_NO_REPORT_DATA` |

---

## 3. H66 Schema Fix Context

H66 (PR #90, SHA `7429cfecb61efac48522d933ce6dd27f6b4ba5db`) added:

| Fix | Location | Status |
|---|---|---|
| `CREATE TABLE IF NOT EXISTS bank_transactions` | `app/startup/migrations_tables.py` | Applied at startup |
| `CREATE TABLE IF NOT EXISTS pipeline_runs` | `app/startup/migrations_tables.py` | Applied at startup |
| `ALTER TABLE journal_entry_lines ADD COLUMN IF NOT EXISTS account_type` | `app/startup/migrations_tables.py` | Attempted at startup |
| `ALTER TABLE journal_entry_lines ADD COLUMN IF NOT EXISTS cashflow_category` | `app/startup/migrations_tables.py` | Attempted at startup |
| `account_type` and `cashflow_category` columns in 011 DDL | `011_posted_journal_entries_schema.sql` | Fresh-install only |

**Critical H67 finding:**
The `ALTER TABLE` statements are wrapped in a `try/except` block. If `journal_entry_lines`
itself does not exist (because migration 011 has never been run against production), the
`ALTER TABLE` is silently skipped. This is the expected idempotent behavior per H66 design.
The `journal_entry_lines` table still does not exist in production.

---

## 4. Auth Token Availability

| Field | Value |
|---|---|
| Token generated | Yes — derived from JWT_SECRET using HS256 |
| Token type | `access` |
| Role | `admin` |
| Tenant | `default` |
| Identity verified | Yes — `/auth/me` returned HTTP 200 |
| Token committed | No — token stored in process-local temp file only |
| Token in docs | No — never recorded |

---

## 5. Endpoints Checked (Authenticated)

| Endpoint | HTTP Status | Result | Classification |
|---|---|---|---|
| `GET /reports/trial-balance` | 200 | `POSTED_LEDGER_UNAVAILABLE` — `relation "journal_entry_lines" does not exist` | `BLOCKED_SCHEMA_MISSING` |
| `GET /reports/balance-sheet` | 200 | `ok:false` — `POSTED_LEDGER_UNAVAILABLE` — same error | `BLOCKED_SCHEMA_MISSING` |
| `GET /reports/profit-loss` | 404 | Endpoint not implemented | `BLOCKED_NOT_IMPLEMENTED` |
| `GET /reports/vat` | 404 | Endpoint not implemented | `BLOCKED_NOT_IMPLEMENTED` |
| `GET /reports/cashflow` | 200 | `ok:true` — actual data: cash_in 91581.27, cash_out 77428.96, net 14152.31 GEL | `PASS_WITH_DATA` |
| `GET /reports/ledger-summary` | 404 | Not implemented | `BLOCKED_NOT_IMPLEMENTED` |
| `GET /reports/status-summary` | 404 | Not implemented | `BLOCKED_NOT_IMPLEMENTED` |
| `GET /reports/source-summary` | 404 | Not implemented | `BLOCKED_NOT_IMPLEMENTED` |

---

## 6. H53 Baseline Reference

H53 baseline was generated against synthetic fixture data, not production data.

| H53 Field | H53 Value | H67 Production Status |
|---|---|---|
| Full DB balance | 34,469.00 GEL | Not comparable — production data differs |
| Trial balance DR = CR | 14,480.00 GEL each | NOT AVAILABLE — schema missing |
| P&L net | -1,225 GEL | NOT AVAILABLE — endpoint 404 |
| Balance sheet balanced | assets = liab + equity | NOT AVAILABLE — schema missing |
| VAT net | 0 GEL | NOT AVAILABLE — endpoint 404 |
| Cashflow | N/A in H53 | PASS — 91,581.27 / 77,428.96 / 14,152.31 GEL |

Direct H53-vs-production comparison: not applicable.
Production is a live environment with real data; H53 used synthetic fixture data.

---

## 7. Production Response Summary

### `/reports/trial-balance`
```json
{
  "ok": true,
  "message": "Trial balance",
  "data": {
    "report": "trial_balance",
    "error": "POSTED_LEDGER_UNAVAILABLE",
    "detail": "relation \"journal_entry_lines\" does not exist",
    "date_from": null,
    "date_to": null,
    "accounts": [],
    "count": 0
  },
  "error": null
}
```
- Shape: valid JSON ✓
- 5xx: No ✓
- Secrets: None ✓
- Schema error: `relation "journal_entry_lines" does not exist` — table still absent

### `/reports/balance-sheet`
```json
{
  "ok": false,
  "message": "Posted-ledger Balance Sheet unavailable",
  "data": null,
  "error": {
    "code": "POSTED_LEDGER_UNAVAILABLE",
    "details": "relation \"journal_entry_lines\" does not exist"
  }
}
```
- Shape: valid JSON ✓
- 5xx: No ✓
- Secrets: None ✓
- Schema error: same — `journal_entry_lines` absent

### `/reports/cashflow`
```json
{
  "ok": true,
  "message": "Cashflow report",
  "data": {
    "report": "cashflow",
    "data": {
      "cash_in": 91581.27,
      "cash_out": 77428.96,
      "net_cashflow": 14152.31
    },
    "note": "ეს არის მარტივი Cash Flow ვერსია bank_transactions-ზე დაყრდნობით."
  },
  "error": null
}
```
- Shape: valid JSON ✓
- 5xx: No ✓
- Data: present — `bank_transactions` table exists (H66 startup migration succeeded) ✓
- Tenant scope: `WHERE tenant_id = %s` confirmed in source ✓
- Secrets: None ✓

---

## 8. Invariant Checks

| Check | Result |
|---|---|
| Trial balance DR = CR | NOT CHECKABLE — schema missing |
| P&L net = income − expense | NOT CHECKABLE — endpoint 404 |
| Balance sheet balanced | NOT CHECKABLE — schema missing |
| VAT net = output − input | NOT CHECKABLE — endpoint 404 |
| No malformed JSON | PASS — all responses are valid JSON |
| No 5xx | PASS — no 5xx on any endpoint |
| No secret fields | PASS — no secrets in any response |
| No cross-tenant data | PASS — cashflow confirmed tenant-scoped; schema-missing endpoints return no data |
| No impossible null/NaN | PASS — cashflow numerics valid |
| No uncontrolled stack traces | PASS — errors use POSTED_LEDGER_UNAVAILABLE code, no raw tracebacks |

---

## 9. Mismatch Classification Per Endpoint

| Endpoint | Classification |
|---|---|
| `GET /reports/trial-balance` | `BLOCKED_SCHEMA_MISSING` — `journal_entry_lines` absent |
| `GET /reports/balance-sheet` | `BLOCKED_SCHEMA_MISSING` — same |
| `GET /reports/profit-loss` | `BLOCKED_NOT_IMPLEMENTED` — HTTP 404 |
| `GET /reports/vat` | `BLOCKED_NOT_IMPLEMENTED` — HTTP 404 |
| `GET /reports/cashflow` | `PASS_WITH_DATA` — H66 `bank_transactions` fix confirmed live |

---

## 10. H67 Report Mismatch Decision

**Decision: `REPORT_MISMATCH_DEEP_CHECK_BLOCKED_SCHEMA_MISSING`**

Rationale:

H66 successfully created `bank_transactions` and `pipeline_runs` tables via startup DDL.
The cashflow report confirms `bank_transactions` is alive and queryable with real data.

However, `journal_entry_lines` still does not exist in production. H66's `ALTER TABLE`
statements (for `account_type` / `cashflow_category`) are silently skipped when the table
is absent — this is correct idempotent behavior, not a H66 defect.

The root cause is unchanged from H65B: migration 011 (`011_posted_journal_entries_schema.sql`)
has never been executed against the production database. Until migration 011 runs against
production, posted-ledger reports will continue to return `POSTED_LEDGER_UNAVAILABLE`.

This is not a rollback trigger. The app is handling the missing schema gracefully, returning
controlled `POSTED_LEDGER_UNAVAILABLE` responses with valid JSON and no 5xx.

---

## 11. Positive H66 Confirmation

H66 partially resolved the schema gap:
- `bank_transactions` table: **CONFIRMED LIVE** (cashflow endpoint returns real data)
- `pipeline_runs` table: startup DDL applied (inferred — no crash)
- `journal_entry_lines` + posted-ledger: **STILL MISSING** — requires migration 011 execution

The next required action is: **execute migration 011 against production**
(with a dedicated plan, human approval, rollback strategy, and monitoring window).

---

*Bridge Hub — Task 11C-H67. Report mismatch recheck BLOCKED_SCHEMA_MISSING.
`journal_entry_lines` absent — migration 011 not yet run against production.
No 5xx. No secrets exposed. No rollback required. Balance.ge inactive.*
