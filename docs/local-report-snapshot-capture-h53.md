# Bridge Hub — H53 Local Report Snapshot Capture

## 1. Purpose

This document records the local report snapshot capture performed in H53 as part of the H53-H57 bundle. H53 recreated the approved disposable local Docker PostgreSQL environment (bridge-hub-h53-postgres, 127.0.0.1:55433), loaded the approved synthetic fixture, and captured SQL-based report snapshots for comparison against the fixture `expected_reports` section. No production DB was touched. No Cloud Run env was mutated.

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
| H52 live SHA | 1f02aba720bf72f60da038808173562bc7ec4a12 |

Approval valid — expires_at 2026-05-25T16:00:00Z not reached (captured 2026-05-18).

---

## 3. Preflight Results

| Check | Expected | Actual | Result |
|---|---|---|---|
| Approval valid | not expired | 2026-05-25T16:00:00Z — valid | ✅ PASS |
| Fixture SHA-256 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 | ✅ PASS |
| Migration SHA-256 | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA | ✅ PASS |
| Docker context | desktop-linux (local) | desktop-linux — npipe local | ✅ PASS |
| No prior H52 container | absent | absent — confirmed | ✅ PASS |
| POSTED_LEDGER_REPORTS_ENABLED | OFF | not set | ✅ PASS |

---

## 4. Local DB Target

| Field | Value |
|---|---|
| Container | bridge-hub-h53-postgres |
| Volume | bridge-hub-h53-pgdata |
| Image | postgres:16 |
| Port | 127.0.0.1:55433 → 5432 (localhost-only) |
| DB | bridge_hub_h53 |
| User | bridge_hub_h53 |
| Cloud SQL | NOT connected |
| Production DB | NOT connected |

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

Captured using `scripts/capture_h53_local_report_snapshots.py`:
- Guard: `H53_LOCAL_DRY_RUN=1` required (aborts without)
- Host/port: `127.0.0.1:55433` only (aborts for any other)
- SHA-256 verified before any insert
- No FastAPI, app startup, or runtime imports
- No external network or production API calls
- `POSTED_LEDGER_REPORTS_ENABLED=` (empty/OFF)

---

## 7. Snapshot Outputs

### Full Balance (all entries, all tenants)
| Metric | Value |
|---|---|
| total_debit | 34,469.00 GEL |
| total_credit | 34,469.00 GEL |
| difference | 0.00 GEL |
| balanced | ✅ True |

### Standard-Net Volume (tenant_alpha, posted + correction)
| Metric | Value |
|---|---|
| total_volume_dr | 23,945.00 GEL |
| total_volume_cr | 23,945.00 GEL |
| balanced | ✅ True |

### Trial Balance by Account (tenant_alpha, standard-net)

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

**Trial Balance DR column: 14,480.00 GEL | CR column: 14,480.00 GEL | Net: 0.00 ✅**

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
| balance check | 10,955.00 = 2,180.00 + 8,775.00 ✅ |

### VAT Register (tenant_alpha, standard-net)
| Metric | Value |
|---|---|
| vat_input_reclaimable | 180.00 GEL |
| vat_output_payable | 180.00 GEL |
| net_vat_position | 0.00 GEL |

### Status Summary
| Status | Count |
|---|---|
| posted | 12 |
| correction | 1 |
| reversed | 1 |
| voided | 1 |
| Total | 15 |

### Tenant Summary
| Tenant | Headers | Lines | total_dr | total_cr |
|---|---|---|---|---|
| tenant_alpha | 14 | 31 | 24,470.00 GEL | 24,470.00 GEL |
| tenant_beta | 1 | 2 | 9,999.00 GEL | 9,999.00 GEL |

### Source Summary
| source_type | count |
|---|---|
| invoice | 2 |
| payroll | 1 |
| draft | 1 |

### Correction/Reversal Summary
| Metric | Value |
|---|---|
| correction_count | 2 |
| reversal_count | 1 |

---

## 8. Safety Notes

- All data synthetic — no real PII, no production data.
- DB: 127.0.0.1:55433 (local Docker only). Cloud SQL: NOT connected.
- `POSTED_LEDGER_REPORTS_ENABLED` not set during capture.
- No Cloud Run endpoints called. No authenticated APIs called.
- No runtime app code, fixture JSON, or migration SQL changed.

---

## 9. Final Capture Decision

**H53 Snapshot Capture Decision: `SNAPSHOT_CAPTURE_COMPLETE`**

52 rows loaded. 10/10 comparison checks PASS against fixture `expected_reports`. Full balance 34,469.00 GEL. Standard-net volume 23,945.00 GEL. Cleanup complete.
