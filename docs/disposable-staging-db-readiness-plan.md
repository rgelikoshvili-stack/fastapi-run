# Bridge Hub — Disposable/Staging DB Readiness Plan

## 1. Purpose

Task 11C-H22 defines the readiness plan for obtaining or confirming a disposable
or staging database suitable for applying the posted-ledger schema migration and
loading synthetic test data before any non-production feature flag switch.

Based on the current known state from H21:

- Staging service existence: not confirmed
- Staging DB existence: not confirmed
- Disposable local/test PostgreSQL: was unavailable in H12; not re-confirmed
- Safe test data: not confirmed

**H22 is docs and contract tests only.**

- H22 does not create a disposable or staging database.
- H22 does not connect to any database.
- H22 does not execute any SQL or migration.
- H22 does not enable any feature flag.
- H22 does not change production or Cloud Run config.
- H22 does not activate Balance.ge.
- H22 does not change credentials, connector behavior, or infrastructure.

---

## 2. Background / H1–H21 Chain

| Task | Description |
|---|---|
| H1  | Found report ledger integrity risks |
| H2  | Defined posted-ledger schema contract |
| H3  | Defined safe schema migration plan |
| H4  | SQL migration contract; not executed |
| H5  | Defined posting service ledger write contract |
| H6  | Added posting ledger write mock tests |
| H7  | Defined report posted-ledger read contract |
| H8  | Added report query mock tests |
| H9  | Defined reversal/correction contract |
| H10 | Defined evidence/audit export linkage |
| H11 | Defined controlled local/test migration execution plan |
| H12 | Attempted local/test migration; blocked — disposable PostgreSQL unavailable |
| H13 | Defined runtime report migration plan with feature flag gate |
| H14 | Added report service query mock tests |
| H15 | Added feature-flagged posted-ledger path; production default OFF |
| H16 | Verified posted-ledger behavior with local/test fixture data |
| H17 | Verified UI/API drill-down contracts |
| H18 | Defined controlled non-production switch plan and production guard |
| H19 | Defined production migration approval plan |
| H20 | Defined staging environment readiness plan |
| H21 | Made staging infrastructure / test data readiness decision — verdict NO-GO |
| H22 | Defines disposable/staging DB readiness plan (this document) |

---

## 3. Non-Action Statement

H22 takes no action beyond producing this readiness plan document:

- No disposable or staging database is created.
- No database is connected.
- No SQL is executed.
- No migration is executed.
- No production DB connection.
- No Cloud Run DB connection.
- No staging Cloud Run service created.
- No feature flag enablement anywhere.
- No Balance.ge activation.
- No credentials changed.
- No connector behavior changed.
- No infrastructure changed.
- No runtime code changes.
- No UI or static file changes.
- H22 does not start H23.

---

## 4. Decision: Is Disposable PostgreSQL Available?

H22 documents two paths depending on whether a disposable local or test
PostgreSQL instance is available.

| Condition | Path |
|---|---|
| Disposable/local PostgreSQL IS available | Case A — apply schema migration, load synthetic test data, document readiness |
| Disposable/local PostgreSQL is NOT available | Case B — define infrastructure readiness path to obtain an isolated DB |
| Staging DB IS available (separate from production) | Case A — treat as disposable DB and apply migration |
| Only production DB exists | Case B — block; must not touch production DB |

**Current known state (from H21):** Disposable PostgreSQL was unavailable in H12
and has not been re-confirmed as available.  Case B path must be documented as the
contingency.  If a disposable DB is confirmed available before H22 is actioned,
Case A applies.

---

## 5. Case A: Disposable PostgreSQL Available — Schema Migration Plan

If a disposable local or staging PostgreSQL is confirmed available and isolated
from production, the following ordered steps apply:

1. **Confirm isolation** — verify DB host, project, or instance name differs from
   the production DB.  Do not proceed if any doubt remains.
2. **Apply migration 011** — run `app/storage/migrations/011_posted_journal_entries_schema.sql`
   against the disposable DB only.  This is an idempotent, additive-only migration.
3. **Verify schema** — confirm `journal_entry_headers`, `journal_entry_lines`, and
   `journal_entry_sources` tables exist with all required columns.
4. **Load synthetic test data** — insert synthetic/anonymized rows meeting the
   requirements in Section 9.  No real customer financial data.
5. **Validate test data** — run the schema validation checklist in Section 8
   against the loaded data.
6. **Document readiness** — record DB host/identifier, migration result, and data
   load confirmation.  File the evidence required by H21 Section 6 before any
   staging switch is attempted.

No production connection at any step.  The migration must be run in the disposable
DB only.

---

## 6. Case B: Disposable PostgreSQL Unavailable — Infrastructure Readiness Path

If no disposable or staging PostgreSQL is available, the following infrastructure
readiness steps must be completed before any staging switch:

1. **Obtain a disposable/local PostgreSQL** — options include:
   - Local Docker container: `docker run -e POSTGRES_PASSWORD=test -p 5432:5432 postgres:15`
   - Cloud SQL staging instance (isolated, non-production project)
   - CI-provisioned ephemeral PostgreSQL (e.g., GitHub Actions service container)
2. **Confirm isolation** — the new DB must not share project, VPC, or credentials
   with the production Cloud SQL instance.
3. **Document the DB** — record host, port, database name, and isolation proof
   before proceeding to Case A steps.
4. **Proceed to Case A** — once the DB is confirmed isolated and available, follow
   Case A steps 2–6.

H22 does not provision any of these options.  Provisioning is the infrastructure
task that follows H22.

---

## 7. Migration File Contract

The schema migration for the posted-ledger tables is documented in:

```
app/storage/migrations/011_posted_journal_entries_schema.sql
```

This file was defined in H4 as a SQL contract and has not been executed against
any database as of H22.

Key properties of the migration file (read-only reference — H22 does not execute it):

- Uses `CREATE TABLE IF NOT EXISTS` — idempotent; safe to run multiple times
- Uses `CREATE INDEX IF NOT EXISTS` — idempotent; safe to run multiple times
- Creates three tables: `journal_entry_headers`, `journal_entry_lines`, `journal_entry_sources`
- Additive only — does not remove, modify, or destroy existing data
- Contains no `DROP TABLE`, `DELETE FROM`, `TRUNCATE`, or destructive `UPDATE` statements
- Contains a balance constraint: `CHECK (total_debit = total_credit)` on `journal_entry_headers`
- Contains a status constraint: `CHECK (status IN ('posted', 'reversed', 'correction', 'voided'))` on `journal_entry_headers`
- `journal_entry_lines` has a FK to `journal_entry_headers(id)` with `ON DELETE CASCADE`
- `journal_entry_sources` has a FK to `journal_entry_headers(id)` with `ON DELETE CASCADE`
- Migration idempotency: running it twice must not error or corrupt data

**H22 documents this file for reference only.  H22 does not execute it.**

---

## 8. Schema Validation Checklist

After running the migration in a disposable DB (Case A), verify:

**`journal_entry_headers` table:**
- `id` — primary key
- `tenant_id` — NOT NULL
- `status` — constrained to `posted`, `reversed`, `correction`, `voided`
- `total_debit` — must equal `total_credit` (balance constraint)
- `total_credit` — see above
- `reversal_of_id` — nullable FK to self
- `correction_of_id` — nullable FK to self
- `posting_log_id` — nullable
- `source_draft_id` — nullable
- `evidence_bundle_id` — nullable
- `created_at` — timestamp

**`journal_entry_lines` table:**
- `id` — primary key
- `journal_entry_id` — FK to `journal_entry_headers(id)` ON DELETE CASCADE
- `tenant_id` — NOT NULL
- `account_code` — NOT NULL
- `debit` — numeric
- `credit` — numeric
- `ledger_line_id` — nullable

**`journal_entry_sources` table:**
- Present with FK to `journal_entry_headers(id)` ON DELETE CASCADE

**Indexes:**
- Index on (`tenant_id`, `status`, `created_at`) on `journal_entry_headers`
- Any additional indexes confirmed present

**Constraints:**
- `tenant_id NOT NULL` enforced on all rows
- Status constraint enforced — only valid values accepted
- Balance constraint enforced — debit total equals credit total per entry

---

## 9. Synthetic Test Data Requirements

Before any staging switch, the disposable DB must contain synthetic (not real customer)
test data covering all of the following:

- Posted income entries (at least one per test tenant)
- Posted expense entries
- Posted asset entries
- Posted liability entries
- Posted equity entries
- Correction entries with `correction_of_id` links
- Reversal entries with `reversal_of_id` links
- VAT/tax lines with VAT-relevant account codes
- Cash/bank lines for cashflow classification
- Payroll lines with payroll account codes
- Counterparty links (`counterparty_id` populated)
- Document links (`document_id` populated)
- `evidence_bundle_id` populated on at least one posted entry per tenant
- `posting_log_id` populated on at least one posted entry per tenant
- `source_draft_id` populated on at least one posted entry per tenant
- Forbidden non-posted states excluded: no `draft`, `approved`, `auto_approved`,
  `simulated_success`, `mock_posting`, `dry_run` rows in the posted-ledger tables
- Multi-tenant negative rows: rows from tenant A must not appear in tenant B responses
- At least two distinct test tenants represented in the data

**Decision:** No safe synthetic test data is confirmed as loaded as of H22.
Test data loading follows successful schema migration in a disposable DB.

---

## 10. Report Verification Checklist

After loading synthetic test data, all 11 official report types must be verified
against the posted-ledger path in the disposable/staging environment before
any production approval:

| # | Report Type |
|---|---|
| 1  | Trial Balance |
| 2  | P&L Summary |
| 3  | P&L Detail |
| 4  | Balance Sheet Summary |
| 5  | Balance Sheet Detail |
| 6  | VAT Register |
| 7  | Account Ledger |
| 8  | Counterparty Ledger |
| 9  | Payroll Ledger |
| 10 | Journal Entries List |
| 11 | Cashflow |

For each report:
- Tenant filter verified: only rows for the requested `tenant_id` returned
- Period/date filter verified: result respects the requested date range
- Old-vs-new comparison: legacy result compared to posted-ledger result; variance documented
- Drill-down verified: `ledger_line_id` → `journal_entry_id` → `source_draft_id` → `posting_log_id` → `evidence_bundle_id`
- No raw secrets: `api_key`, `password`, `token`, `secret` absent from all response payloads

---

## 11. Feature Flag Decision

Rules for `POSTED_LEDGER_REPORTS_ENABLED` that apply during and after H22:

| Rule | Detail |
|---|---|
| Production remains OFF | Must remain OFF at all times during H22 and until all H19 approval gates satisfied |
| Disposable/local only | Feature flag may be enabled in disposable/local DB environment only after schema and data are confirmed |
| Staging allowance | Staging can enable only with explicit approval and documented evidence from H21 Section 6 |
| Unknown environment | Fail-closed — unrecognised environment name treated as production-safe; flag treated as OFF |
| Rollback | Set `POSTED_LEDGER_REPORTS_ENABLED=""` — legacy path resumes in one restart |
| No silent fallback | `_assert_no_silent_fallback` enforced — `journal_drafts` must never appear in posted-ledger queries |
| Fail-closed on unavailable tables | If `journal_entry_headers` or `journal_entry_lines` absent → `POSTED_LEDGER_UNAVAILABLE`; no silent fallback |

---

## 12. Security / Privacy Requirements

All of the following must be satisfied before any staging or disposable DB switch:

| Requirement | Detail |
|---|---|
| No production credentials | Disposable DB must not share production DB password, API keys, or service account |
| No real customer data | Synthetic or anonymized data only — no production customer financial rows |
| Tenant isolation enforced | `tenant_id` mandatory on all rows; cross-tenant access forbidden |
| RBAC enabled | `require_permission` enforced on all report and drilldown endpoints |
| 401/403 behavior verified | Unauthenticated/unauthorised requests blocked |
| No raw secrets in payloads | `api_key`, `password`, `token`, `secret` absent from all report responses |
| Evidence bundle access scoped | `evidence_bundle_id` accessible only to owning `tenant_id` |
| Posting log access scoped | `posting_log_id` accessible only to owning `tenant_id` |
| Audit trail access scoped | `audit_event_id` accessible only to owning `tenant_id` |
| No production DB connection | H22 does not connect to production DB under any circumstances |

---

## 13. Go / No-Go

**GO criteria** — all must be true before any staged switch:

- Disposable/staging PostgreSQL confirmed available and isolated from production
- Schema migration 011 applied successfully in disposable DB only
- `journal_entry_headers`, `journal_entry_lines`, `journal_entry_sources` present and validated
- Synthetic test data loaded and validated against all requirements in Section 9
- No production credentials used in the disposable DB environment
- Feature flag default OFF before any test window
- Rollback confirmed — unset flag restores legacy path in one restart
- Migration idempotency verified — running migration twice produces no error or data corruption

**NO-GO criteria** — any one of these blocks the switch:

- No disposable or staging PostgreSQL available (Case B applies)
- DB is or may be the production database
- Schema migration not yet applied in disposable DB
- Synthetic test data not loaded
- Real customer financial data present in any test/disposable DB
- Production credentials reused in disposable/staging environment
- Feature flag would affect production
- Balance.ge would be live (not `demo_mode`)
- Disposable PostgreSQL remains unavailable (Case B — infrastructure task required first)

**Current verdict: NO-GO** — disposable PostgreSQL availability not re-confirmed;
schema migration not applied; synthetic test data not loaded.

---

## 14. Non-Goals for H22

This task does **not**:

- Create a disposable or staging database
- Connect to any database
- Execute any SQL or migration
- Enable any feature flag
- Execute any production switch or staging switch
- Change any Cloud Run environment variables
- Activate Balance.ge or any ERP connector
- Change any connector behavior or credentials
- Change any infrastructure
- Change any runtime code
- Change any UI or static files
- Change posting or approval logic
- Start H23

---

## 15. Recommended Next Path

Based on the current known state from H21 and H22:

**If a disposable PostgreSQL is confirmed available:**

**11C-H23 — Disposable DB Schema Migration and Test Data Load**

This task should apply migration 011 to the confirmed disposable DB, load
synthetic test data, and document readiness per the evidence checklist in H21
Section 6.

**If no disposable PostgreSQL is available (current known state):**

**11C-H23 — Disposable PostgreSQL Infrastructure Setup**

This task should provision an isolated local or staging PostgreSQL instance
(Docker, Cloud SQL staging, or CI ephemeral), confirm isolation from production,
and then proceed with schema migration and data load.

Do not proceed to any staged feature flag switch until all GO criteria in
Section 13 are satisfied.

---

## 16. Next Task

Only after PR merge, deploy, and live verification:

**Preferred:**
**11C-H23 — Disposable DB Schema Migration and Test Data Load** (if disposable DB available)

**Alternative if disposable DB is unavailable:**
**11C-H23 — Disposable PostgreSQL Infrastructure Setup**

H22 does not start H23.  H23 begins only after this PR is merged, deployed to
Cloud Run, and live-verified via `/version` and `/health`.
