# Bridge Hub — H53 Local Report Snapshot Capture

## 1. Purpose

This document records the local report snapshot capture performed in H53. H53 recreated the approved disposable local Docker PostgreSQL environment (bridge-hub-h53-postgres, 127.0.0.1:55433), loaded the approved synthetic fixture, and captured SQL-based report snapshots for comparison against the fixture's `expected_reports` section. No production DB was touched. No Cloud Run env was mutated.

**H53 does NOT connect to production DB.**
**H53 does NOT mutate Cloud Run env vars.**
**H53 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED` in production.**
**H53 does NOT activate Balance.ge.**
**H53 does NOT call authenticated runtime report APIs.**

---

## 2. Approval Reference

| Field | Value |
|---|---|
| approval_id | APPROVAL-2026-H50-001 |
| approved_by | ROLANDI GELIKOSHVILI |
| approved_by_email | r.gelikoshvili@gmail.com |
| scope | local_docker_postgres_dry_run_only |
| approved_at | 2026-05-18T16:00:00Z |
| expires_at | 2026-05-25T16:00:00Z |
| approval_status | OWNER_APPROVAL_SIGNED |
| H52 decision | SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE |
| H52 live SHA | 1f02aba720bf72f60da038808173562bc7ec4a12 |

Approval is valid. expires_at 2026-05-25T16:00:00Z has not been reached (captured 2026-05-18).

---

## 3. Preflight Check Results

| Check | Expected | Actual | Pass/Fail |
|---|---|---|---|
| Approval valid | expires 2026-05-25 | 2026-05-25T16:00:00Z — not expired | ✅ PASS |
| Fixture SHA-256 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 | ✅ PASS |
| Migration SHA-256 | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA | ✅ PASS |
| Docker context | desktop-linux (local) | desktop-linux — npipe local pipe | ✅ PASS |
| No H53 container pre-existing | absent | absent — confirmed before run | ✅ PASS |
| POSTED_LEDGER_REPORTS_ENABLED | OFF/absent | not set | ✅ PASS |

---

## 4. Local DB Target

| Field | Value |
|---|---|
| Container name | bridge-hub-h53-postgres |
| Volume name | bridge-hub-h53-pgdata |
| Image | postgres:16 |
| Port | 127.0.0.1:55433 → 5432 (localhost-only bind) |
| DB name | bridge_hub_h53 |
| DB user | bridge_hub_h53 |
| DB host | 127.0.0.1 (local Docker only) |
| Cloud SQL | NOT connected |
| Production DB | NOT connected |

No production or Cloud Run DB was connected at any point.

---

## 5. Migration / Fixture Proof

| Item | Value |
|---|---|
| Migration path | app/storage/migrations/011_posted_journal_entries_schema.sql |
| Migration SHA-256 | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA |
| Objects created | journal_entry_headers, journal_entry_lines, journal_entry_sources + 14 indexes |
| Fixture path | tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json |
| Fixture SHA-256 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 |
| Rows loaded | 15 headers + 33 lines + 4 sources = 52 total |

---

## 6. Snapshot Capture Method

Snapshots were captured using `scripts/capture_h53_local_report_snapshots.py` — a local-only helper that:
- Requires `H53_LOCAL_DRY_RUN=1` env guard (aborts without it)
- Requires `DATABASE_URL` pointing to `127.0.0.1:55433` only (aborts for any other host/port)
- Verifies fixture SHA-256 before any insert
- Does not import FastAPI, app startup, or any runtime service
- Does not call any external network or production API
- Uses psycopg2 only

Guard vars set during capture:
- `H53_LOCAL_DRY_RUN=1`
- `DATABASE_URL=postgresql://bridge_hub_h53:***@127.0.0.1:55433/bridge_hub_h53`
- `POSTED_LEDGER_REPORTS_ENABLED=` (empty / OFF)

---

## 7. SQL Queries Used

### Query 1 — Trial Balance by Account (tenant_alpha, standard-net)
```sql
SELECT l.account_code, l.account_name,
  SUM(l.debit) AS sum_dr, SUM(l.credit) AS sum_cr,
  SUM(l.debit)-SUM(l.credit) AS net_balance, COUNT(*) AS line_count
FROM journal_entry_lines l
JOIN journal_entry_headers h ON h.id = l.journal_entry_id
WHERE h.tenant_id = 'tenant_alpha'
  AND h.status IN ('posted','correction')
GROUP BY l.account_code, l.account_name
ORDER BY l.account_code;
```

### Query 2 — Total Volume Check (tenant_alpha, standard-net)
```sql
SELECT SUM(l.debit) AS total_volume_dr, SUM(l.credit) AS total_volume_cr
FROM journal_entry_lines l
JOIN journal_entry_headers h ON h.id = l.journal_entry_id
WHERE h.tenant_id = 'tenant_alpha' AND h.status IN ('posted','correction');
```

### Query 3 — P&L Summary (tenant_alpha, standard-net)
```sql
SELECT
  SUM(CASE WHEN l.account_code LIKE '4%' THEN l.credit - l.debit ELSE 0 END) AS total_income,
  SUM(CASE WHEN l.account_code LIKE '5%' THEN l.debit - l.credit ELSE 0 END) AS total_expense,
  SUM(CASE WHEN l.account_code LIKE '4%' THEN l.credit - l.debit ELSE 0 END)
  - SUM(CASE WHEN l.account_code LIKE '5%' THEN l.debit - l.credit ELSE 0 END) AS net_profit_loss
FROM journal_entry_lines l
JOIN journal_entry_headers h ON h.id = l.journal_entry_id
WHERE h.tenant_id = 'tenant_alpha' AND h.status IN ('posted','correction');
```

### Query 4 — Balance Sheet (tenant_alpha, standard-net)
```sql
SELECT
  SUM(CASE WHEN l.account_code LIKE '1%' THEN l.debit - l.credit ELSE 0 END) AS total_assets,
  SUM(CASE WHEN l.account_code LIKE '2%' THEN l.credit - l.debit ELSE 0 END) AS total_liabilities,
  SUM(CASE WHEN l.account_code LIKE '3%' THEN l.credit - l.debit ELSE 0 END) AS equity_share_capital
FROM journal_entry_lines l
JOIN journal_entry_headers h ON h.id = l.journal_entry_id
WHERE h.tenant_id = 'tenant_alpha' AND h.status IN ('posted','correction');
```

### Query 5 — VAT Register (tenant_alpha, standard-net)
```sql
SELECT
  SUM(CASE WHEN l.account_code='1211' THEN l.debit ELSE 0 END) AS vat_input_reclaimable,
  SUM(CASE WHEN l.account_code='2200' THEN l.credit ELSE 0 END) AS vat_output_payable
FROM journal_entry_lines l
JOIN journal_entry_headers h ON h.id = l.journal_entry_id
WHERE h.tenant_id = 'tenant_alpha' AND h.status IN ('posted','correction');
```

### Query 6 — Tenant Isolation
```sql
SELECT h.tenant_id, COUNT(*) as line_cnt, SUM(l.debit) as dr, SUM(l.credit) as cr
FROM journal_entry_lines l
JOIN journal_entry_headers h ON h.id = l.journal_entry_id
GROUP BY h.tenant_id ORDER BY h.tenant_id;
```

### Query 7 — Full Balance (all entries, all tenants)
```sql
SELECT SUM(debit) AS total_debit, SUM(credit) AS total_credit,
       SUM(debit)-SUM(credit) AS difference
FROM journal_entry_lines;
```

---

## 8. Snapshot Outputs Summary

### Full Balance (all entries, all tenants)
| Metric | Value |
|---|---|
| total_debit | 34,469.00 GEL |
| total_credit | 34,469.00 GEL |
| difference | 0.00 GEL |
| balanced | ✅ True |

### Trial Balance by Account (tenant_alpha, standard-net: posted + correction)

| Account | Name | sum_dr | sum_cr | net_balance | Lines |
|---|---|---|---|---|---|
| 1010 | Bank (Synthetic) | 11,180.00 | 6,705.00 | +4,475.00 DR | 8 |
| 1200 | AR (Synthetic) | 2,680.00 | 1,380.00 | +1,300.00 DR | 4 |
| 1211 | VAT Input (Synthetic) | 180.00 | 0.00 | +180.00 DR | 1 |
| 1500 | Fixed Assets (Synthetic) | 5,000.00 | 0.00 | +5,000.00 DR | 1 |
| 2100 | AP (Synthetic) | 1,180.00 | 1,180.00 | 0.00 | 2 |
| 2200 | VAT Payable (Synthetic) | 0.00 | 180.00 | -180.00 CR | 1 |
| 2300 | Salary Payable (Synthetic) | 0.00 | 1,600.00 | -1,600.00 CR | 1 |
| 2310 | Tax Payable PAYG (Synthetic) | 0.00 | 400.00 | -400.00 CR | 1 |
| 3000 | Share Capital (Synthetic) | 0.00 | 10,000.00 | -10,000.00 CR | 1 |
| 4100 | Service Revenue (Synthetic) | 200.00 | 2,000.00 | -1,800.00 CR | 3 |
| 4200 | Product Revenue (Synthetic) | 0.00 | 500.00 | -500.00 CR | 1 |
| 5100 | Office Expense (Synthetic) | 1,500.00 | 0.00 | +1,500.00 DR | 2 |
| 5200 | Salary Expense (Synthetic) | 2,000.00 | 0.00 | +2,000.00 DR | 1 |
| 5300 | Bank Fees (Synthetic) | 25.00 | 0.00 | +25.00 DR | 1 |

**Trial Balance DR column total: 14,480.00 GEL**
**Trial Balance CR column total: 14,480.00 GEL**
**Net sum: 0.00 — balanced ✅**

### Total Volume (tenant_alpha, standard-net)
- total_volume_dr = 23,945.00 GEL ✅
- total_volume_cr = 23,945.00 GEL ✅

### Status Summary (all tenants)
| Status | Count |
|---|---|
| posted | 12 |
| correction | 1 |
| reversed | 1 |
| voided | 1 |
| **Total** | **15** |

### Tenant Summary
| Tenant | Headers | Lines | total_debit | total_credit |
|---|---|---|---|---|
| tenant_alpha | 14 | 31 | 24,470.00 GEL | 24,470.00 GEL |
| tenant_beta | 1 | 2 | 9,999.00 GEL | 9,999.00 GEL |

### P&L Summary (tenant_alpha, standard-net)
| Metric | Value |
|---|---|
| total_income | 2,300.00 GEL |
| total_expense | 3,525.00 GEL |
| net_profit_loss | -1,225.00 GEL (net loss) |

### Balance Sheet (tenant_alpha, standard-net)
| Metric | Value |
|---|---|
| total_assets | 10,955.00 GEL |
| total_liabilities | 2,180.00 GEL |
| equity_share_capital | 10,000.00 GEL |
| equity_total (capital + retained) | 8,775.00 GEL |
| check: assets = liabilities + equity | 10,955.00 = 2,180.00 + 8,775.00 ✅ |

### VAT Register (tenant_alpha, standard-net)
| Metric | Value |
|---|---|
| vat_input_reclaimable | 180.00 GEL |
| vat_output_payable | 180.00 GEL |
| net_vat_position | 0.00 GEL |

### Correction/Reversal Summary
| Metric | Value |
|---|---|
| correction_count (correction_of_entry_id IS NOT NULL) | 2 |
| reversal_count (reversed_by_entry_id IS NOT NULL) | 1 |
| linked_entry_count | 3 |

### Source Summary
| source_type | count |
|---|---|
| draft | 1 |
| invoice | 2 |
| payroll | 1 |

---

## 9. Safety Notes

- All data is synthetic — no real PII, no production data.
- DB target was 127.0.0.1:55433 (local Docker only).
- `POSTED_LEDGER_REPORTS_ENABLED` was not set during capture.
- No Cloud Run endpoints were called.
- No authenticated production APIs were called.
- No runtime app code was changed.
- No fixture JSON was changed.
- No migration SQL was changed.

---

## 10. Final Capture Decision

**H53 Snapshot Capture Decision: `SNAPSHOT_CAPTURE_COMPLETE`**

All 7 report queries executed successfully against the local disposable DB. Full balance confirmed (34,469.00 GEL across all entries; 23,945.00 GEL standard-net volume for tenant_alpha). All snapshots available for comparison. See [local-report-snapshot-comparison-h53.md](local-report-snapshot-comparison-h53.md) for comparison results.
