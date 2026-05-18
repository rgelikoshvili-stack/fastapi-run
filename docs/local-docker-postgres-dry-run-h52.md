# Bridge Hub — H52 Local Docker PostgreSQL Provisioning Dry-Run

## 1. Purpose

This document records the H52 local Docker PostgreSQL provisioning dry-run execution. H52 is the first approved local execution of the posted ledger schema migration (011) and synthetic fixture loading, using a disposable local Docker PostgreSQL container under the scope of APPROVAL-2026-H50-001.

**H52 does NOT touch production DB.**
**H52 does NOT touch Cloud Run DB.**
**H52 does NOT mutate Cloud Run env vars.**
**H52 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED` in production.**
**H52 does NOT activate Balance.ge.**
**H52 does NOT use production or customer data.**
**H52 does NOT change runtime app code.**

---

## 2. Approval Reference

| Field | Value |
|---|---|
| approval_id | APPROVAL-2026-H50-001 |
| approved_by | ROLANDI GELIKOSHVILI |
| approved_by_email | r.gelikoshvili@gmail.com |
| approved_at | 2026-05-18T16:00:00Z |
| expires_at | 2026-05-25T16:00:00Z |
| scope | local_docker_postgres_dry_run_only |
| status | approved |
| final gate decision (H51) | READY_FOR_LOCAL_DOCKER_POSTGRES_DRY_RUN |

---

## 3. Scope

This dry-run is scoped to:
- Disposable local Docker PostgreSQL container only
- Synthetic fixture data only (no production/customer data)
- Migration 011 execution in disposable local DB only
- Local verification SQL only
- No Cloud Run, no production DB, no real posting, no Balance.ge activation

---

## 4. Preflight Check Results

All Phase 1 preflight checks passed before container creation:

| Check | Expected | Actual | Result |
|---|---|---|---|
| Approval not expired | expires_at 2026-05-25 | current 2026-05-18 | ✅ PASS |
| Fixture SHA-256 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 | ✅ PASS |
| Migration 011 SHA-256 | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA | ✅ PASS |
| Docker context | desktop-linux (local) | desktop-linux — npipe:////./pipe/dockerDesktopLinuxEngine | ✅ PASS |
| No remote/cloud context | required | confirmed — local Windows named pipe | ✅ PASS |
| No production risk | required | none detected | ✅ PASS |

**Phase 1 decision: PASS — proceed to container creation.**

---

## 5. Docker Container Details

| Field | Value |
|---|---|
| Image | postgres:16 (SHA256: b6ccf02e9b47eac0d67b5eaa0ef56fd59163bffa5506f64e96ceb5053130ec86) |
| Container name | bridge-hub-h52-postgres |
| Volume name | bridge-hub-h52-pgdata |
| Port | 127.0.0.1:55432 → 5432 (localhost-only bind) |
| DB name | bridge_hub_h52 |
| DB user | bridge_hub_h52 |
| Password | disposable local-only (not committed) |
| Context | desktop-linux (local Windows named pipe) |
| Container start | ✅ SUCCESS |
| Readiness | pg_isready: accepting connections |
| PostgreSQL version | 16.14 (Debian 16.14-1.pgdg13+1) |

---

## 6. DB Target Proof

- host: 127.0.0.1 (localhost-only)
- port: 55432 (H52-specific port, no collision with local Postgres)
- db: bridge_hub_h52
- user: bridge_hub_h52
- container: bridge-hub-h52-postgres (local Docker only)
- no remote host
- no Cloud SQL
- no Railway / Supabase / external Postgres
- production DATABASE_URL not used

DB confirmed via SQL:

```
current_database | current_user
-----------------+----------------
bridge_hub_h52   | bridge_hub_h52
```

---

## 7. Migration 011 Execution Result

| Field | Value |
|---|---|
| Migration path | app/storage/migrations/011_posted_journal_entries_schema.sql |
| Migration SHA-256 | F552E49703B164FF03656EF09F223F4A3292636423C529890849B06C648AF9BA |
| Executed against | bridge_hub_h52 @ 127.0.0.1:55432 (local Docker only) |
| Status | ✅ SUCCESS |

Objects created by migration 011:

| Object | Type | Details |
|---|---|---|
| journal_entry_headers | TABLE | Immutable posted ledger headers |
| journal_entry_lines | TABLE | Double-entry lines per header |
| journal_entry_sources | TABLE | Source/evidence linkage per header |
| idx_jeh_tenant | INDEX | journal_entry_headers(tenant_id) |
| idx_jeh_tenant_period | INDEX | (tenant_id, period) |
| idx_jeh_tenant_entry_date | INDEX | (tenant_id, entry_date) |
| idx_jeh_tenant_status | INDEX | (tenant_id, status) WHERE posted |
| idx_jeh_tenant_source_draft | INDEX | (tenant_id, source_draft_id) |
| idx_jeh_tenant_posting_log | INDEX | (tenant_id, posting_log_id) |
| idx_jeh_tenant_evidence_bundle | INDEX | (tenant_id, evidence_bundle_id) |
| idx_jel_tenant | INDEX | journal_entry_lines(tenant_id) |
| idx_jel_tenant_journal_entry | INDEX | (tenant_id, journal_entry_id) |
| idx_jel_tenant_account_code | INDEX | (tenant_id, account_code) |
| idx_jel_tenant_counterparty | INDEX | (tenant_id, counterparty_id) |
| idx_jel_tenant_document | INDEX | (tenant_id, document_id) |
| idx_jel_tenant_bank_transaction | INDEX | (tenant_id, bank_transaction_id) |
| idx_jes_tenant_journal_entry | INDEX | journal_entry_sources(tenant_id, journal_entry_id) |

Total: 3 tables + 14 indexes. All CREATE IF NOT EXISTS (idempotent).

---

## 8. Fixture Load Result

| Field | Value |
|---|---|
| Fixture path | tests/fixtures/posted_ledger/synthetic_posted_ledger_fixture_pack.json |
| Fixture SHA-256 | 1F00C0C65F972579D1989AAD9E0FDFF4AB21DDB6A09B7FC1B8AD5B7D85331299 |
| Loader | scripts/load_h52_synthetic_fixture_local_only.py |
| Guard | H52_LOCAL_DRY_RUN=1 (required) |
| Host check | 127.0.0.1:55432 only (rejected non-local hosts) |
| Fixture type | synthetic — no real PII, no production data |
| journal_entry_headers loaded | 15 |
| journal_entry_lines loaded | 33 |
| journal_entry_sources loaded | 4 |
| Total rows committed | 52 |
| Status | ✅ SUCCESS |

---

## 9. Local Verification Results

All verification SQL executed against local Docker container only:

| Check | Result |
|---|---|
| journal_entry_headers row count | 15 ✅ |
| journal_entry_lines row count | 33 ✅ |
| journal_entry_sources row count | 4 ✅ |
| tenant_alpha posted headers | 11 ✅ |
| tenant_alpha correction headers | 1 ✅ |
| tenant_alpha reversed headers | 1 ✅ |
| tenant_alpha voided headers | 1 ✅ |
| tenant_beta posted headers | 1 ✅ (isolation confirmed) |
| Double-entry balance (tenant_alpha, posted+correction) | sum_dr = sum_cr = 23,945.00 GEL ✅ |
| Lines with both debit+credit positive | 0 ✅ |
| Zero-amount lines | 0 ✅ |
| Empty tenant_id rows | 0 ✅ |
| Index count | 14 ✅ |

No production-like PII patterns. No Balance.ge data. No feature flag state.

---

## 10. Cleanup

See: `docs/local-docker-postgres-dry-run-cleanup-h52.md`

| Step | Status |
|---|---|
| docker stop bridge-hub-h52-postgres | ✅ Completed |
| docker rm bridge-hub-h52-postgres | ✅ Completed |
| docker volume rm bridge-hub-h52-pgdata | ✅ Completed |
| Container verified absent | ✅ Confirmed |
| Volume verified absent | ✅ Confirmed |

---

## 11. Final Decision

**H52 Final Decision: `SUCCESS_LOCAL_DOCKER_POSTGRES_DRY_RUN_COMPLETE`**

All phases completed successfully:
- Container created ✅
- Migration 011 executed in disposable local DB ✅
- Synthetic fixture loaded (52 rows) ✅
- Verification passed (all invariants hold) ✅
- Cleanup completed ✅

---

## 12. Next Task

**H53 — Local Report Snapshot Capture / Comparison Dry-Run**

H53 will:
1. Re-create the local disposable container (or use evidence from H52).
2. Run local report queries against the local posted ledger tables.
3. Compare local report output to `expected_reports` in the fixture.
4. Capture report snapshot evidence.
5. Document delta between journal_drafts-based reports and posted-ledger reports.
6. Cleanup.

None of H53's steps are executed in H52.

---

## 13. Safety Confirmation

- No production DB touched.
- No Cloud Run DB touched.
- No Cloud Run env vars mutated.
- No POSTED_LEDGER_REPORTS_ENABLED enabled in production.
- No Balance.ge activated.
- No production or customer data used.
- No real PII.
- No credentials committed.
- No runtime app code changed.
- No UI/static files changed.
- No fixture JSON changed.
- No migration SQL changed.
- No production DATABASE_URL used.
- All data synthetic — confirmed by fixture metadata.
