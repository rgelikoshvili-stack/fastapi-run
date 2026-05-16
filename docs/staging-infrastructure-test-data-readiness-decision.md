# Bridge Hub — Staging Infrastructure / Test Data Readiness Decision

## 1. Purpose

Task 11C-H21 makes the formal readiness decision for how Bridge Hub should proceed
before any staging/non-production posted-ledger report switch.

Based on the current known state, H21 determines whether the next safe task is:
- a controlled staging posted-ledger dry run (if isolated staging already exists), or
- a staging/disposable DB and test data preparation task (if staging or DB is absent).

**H21 is docs and contract tests only.**

- H21 does not create staging infrastructure.
- H21 does not create or connect to DB.
- H21 does not enable any feature flag.
- H21 does not run SQL or migrations.
- H21 does not change production or Cloud Run config.
- H21 does not activate Balance.ge.
- H21 does not change credentials, connector behavior, or infrastructure.

---

## 2. Background / H1–H20 Chain

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
| H21 | Makes staging infrastructure / test data readiness decision (this document) |

---

## 3. Non-Action Statement

H21 takes no action beyond producing this decision document:

- No staging Cloud Run service created.
- No staging DB created or connected.
- No SQL execution.
- No migration execution.
- No production DB connection.
- No Cloud Run DB connection.
- No feature flag enablement anywhere.
- No Balance.ge activation.
- No credentials changed.
- No connector behavior changed.
- No infrastructure changed.
- No runtime code changes.
- No UI or static file changes.
- H21 does not start H22.

---

## 4. Current Known State

As of H21, the following is known:

| Item | State |
|---|---|
| Production Cloud Run service | exists — `fastapi-run`, `europe-west1` |
| Production feature flag (`POSTED_LEDGER_REPORTS_ENABLED`) | OFF / absent — confirmed H20 live check |
| Balance.ge | `demo_mode` — `BALANCE_API_KEY` missing |
| Full unit suite | green — 3877 passed / 0 failed / 2 skipped (H20) |
| Staging service existence | **not confirmed** — no separate staging Cloud Run service verified |
| Staging DB existence | **not confirmed** — no separate staging database verified |
| Disposable local/test PostgreSQL | **unavailable** — H12 blocker; no disposable PostgreSQL confirmed available |
| Safe posted-ledger test data in any DB | **not confirmed** — no synthetic/anonymized test data loaded |
| Old-vs-new report comparison in staging | **not yet run** — requires staging DB and test data |
| `journal_entry_headers`/`journal_entry_lines` in any staging/local DB | **not confirmed** |

**Conclusion:** Based on current known state, the switch prerequisite is the disposable/staging DB and test data readiness path (Case C / Case D below).

---

## 5. Decision Matrix

| Case | Condition | Decision |
|---|---|---|
| Case A | Staging service exists and is isolated from production + staging DB exists and is isolated | Proceed to **controlled staging posted-ledger report switch dry run** |
| Case B | Staging service does not exist | Next task must be **staging infrastructure readiness/design** — do not attempt switch |
| Case C | Staging DB does not exist | Next task must be **staging/disposable DB readiness** — do not attempt switch |
| Case D | Safe test data does not exist | Next task must be **test data readiness preparation** — do not attempt switch |
| Case E | Disposable local/test DB remains unavailable | Next task must be **infrastructure readiness** to resolve DB availability — do not attempt switch |
| Case F | Only production environment exists | **Block switch entirely** — no production testing; staging must be created first |

**Current decision:** Staging service existence is not confirmed; staging DB existence is not confirmed; disposable PostgreSQL was unavailable in H12. **Case C / Case D / Case E applies. Next task: H22 — Disposable/Staging DB Readiness Plan.**

---

## 6. Required Evidence Before Staging Switch

Before any controlled staging posted-ledger switch, the following evidence must be collected and documented:

| Evidence Item | Required |
|---|---|
| Staging service URL or Cloud Run service identifier | yes |
| `ENVIRONMENT=staging` or equivalent environment marker set | yes |
| Staging service account (separate from production) | yes |
| Staging DB identifier (host/project/instance — not production) | yes |
| Proof DB is not production — different host or explicit confirmation | yes |
| Proof no production write credentials in staging service account | yes |
| Synthetic/anonymized test data source — no real customer financial rows | yes |
| Posted ledger tables exist in staging DB (`journal_entry_headers`, `journal_entry_lines`) | yes |
| Migrations applied in staging/local DB only — not production | yes |
| Report endpoints protected (401/403 without auth) in staging | yes |
| Feature flag default OFF before test window | yes |
| Rollback method confirmed — unset flag restores legacy path | yes |
| Monitoring/log labels confirmed — staging logs distinct from production | yes |

---

## 7. Test Data Readiness Decision

Safe test data must cover all of the following before any staging switch:

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
- Forbidden non-posted states excluded (`draft`, `approved`, `auto_approved`, `simulated_success`, `mock_posting`, `dry_run`)
- Multi-tenant negative rows — rows from tenant A must not appear in tenant B responses

**Decision:** No safe test data is confirmed as loaded.  Test data preparation is a prerequisite for staging switch.

---

## 8. Staging DB Readiness Decision

The staging/disposable DB must contain the following before any switch:

- `journal_entry_headers` table present with all required columns
- `journal_entry_lines` table present with all required columns
- `journal_entry_sources` if used by the report service
- `tenant_id NOT NULL` constraint enforced on all rows
- Status constraints — only valid values (`posted`, `correction`, `reversed`, `voided`, `draft`, etc.)
- Indexes on (`tenant_id`, `status`, `created_at`) for report query performance
- Balanced journal constraints — debit total equals credit total per entry
- Evidence/posting/source link columns — `evidence_bundle_id`, `posting_log_id`, `source_draft_id` present (nullable where allowed)
- Rollback does not drop tables — flag controls query path only; tables must be preserved
- Migration idempotency verified — running the migration twice must not error or corrupt data

**Decision:** No staging/disposable DB is confirmed as ready.  DB readiness is a prerequisite for staging switch.

---

## 9. Feature Flag Decision

Rules for `POSTED_LEDGER_REPORTS_ENABLED` that apply to all environments:

| Rule | Detail |
|---|---|
| Production remains OFF | `POSTED_LEDGER_REPORTS_ENABLED` must remain OFF in production at all times during H21 |
| Staging may enable only after evidence checklist | All evidence items from Section 6 must be satisfied before staging switch |
| Local/CI monkeypatch only in tests | Never set as a real process env var in CI config |
| Unknown environment fail-closed | Any unrecognised environment name treated as production-safe; flag treated as OFF |
| Enabled mode cannot fallback to `journal_drafts` | `_assert_no_silent_fallback` enforced in enabled mode |
| Unavailable posted-ledger source returns `POSTED_LEDGER_UNAVAILABLE` | Fail-closed error — no silent fallback on missing tables |
| Rollback | Set `POSTED_LEDGER_REPORTS_ENABLED=""` — legacy path resumes in one restart |

---

## 10. Security / Privacy Decision

All of the following must be verified before any staging switch:

| Requirement | Detail |
|---|---|
| RBAC enabled in staging | `require_permission` enforced on all report/drilldown endpoints |
| 401/403 behavior verified | Unauthenticated/unauthorised requests blocked in staging |
| No cross-tenant access | `tenant_id` mandatory; cross-tenant rows filtered before any report response |
| No raw secrets in payloads | `api_key`, `password`, `token`, `secret` absent from all report responses |
| No production credentials reused | Staging service account must not share production DB password or API keys |
| Evidence bundle access scoped | `evidence_bundle_id` accessible only to owning `tenant_id` |
| Posting log access scoped | `posting_log_id` accessible only to owning `tenant_id` |
| Audit trail access scoped | `audit_event_id` accessible only to owning `tenant_id` |

---

## 11. Recommended Next Path

Based on the current known state documented in Section 4:

- Staging service existence: **not confirmed**
- Staging DB existence: **not confirmed**
- Disposable PostgreSQL availability: **was unavailable in H12; not re-confirmed**
- Safe test data: **not confirmed**

**Recommendation:**

**11C-H22 — Disposable/Staging DB Readiness Plan**

This task should:
1. Determine whether a disposable local/test PostgreSQL is now available.
2. If available: run schema migration in disposable DB, load synthetic test data, and document readiness.
3. If not available: define the infrastructure readiness path to obtain or create an isolated staging/test DB.

Do not proceed to controlled staging switch until staging service, staging DB, and safe test data are confirmed as ready per the evidence checklist in Section 6.

---

## 12. Go / No-Go

**GO criteria** — all must be true before any staging switch:

- Isolated staging service exists (separate from production Cloud Run)
- Isolated staging/disposable DB exists (separate from production DB)
- Safe synthetic/anonymized test data loaded
- Posted ledger schema applied in staging/local DB only
- No production credentials in staging
- Rollback confirmed — unset flag restores legacy path in one restart
- Monitoring and log labels ready
- Owner approval from engineering lead and QA lead

**NO-GO criteria** — any one of these blocks the switch:

- Only production Cloud Run service exists
- Staging DB is absent or is the production DB
- Safe test data is absent
- Disposable local PostgreSQL remains unavailable
- Environment classification unclear
- Feature flag would affect production
- Balance.ge would be live (not `demo_mode`)

**Current verdict: NO-GO** — staging service, staging DB, and safe test data are not yet confirmed.

---

## 13. Non-Goals for H21

This task does **not**:

- Create staging Cloud Run service or any staging infrastructure
- Create staging DB or connect to any database
- Execute any SQL or migration
- Enable any feature flag
- Execute any production switch
- Change any Cloud Run environment variables
- Activate Balance.ge or any ERP connector
- Change any connector behavior or credentials
- Change any infrastructure
- Change any runtime code
- Change any UI or static files
- Change posting or approval logic
- Start H22

---

## 14. Next Task

Only after PR merge, deploy, and live verification:

**Preferred:**
**11C-H22 — Disposable/Staging DB Readiness Plan**

**Alternative if isolated staging already exists and is confirmed:**
**11C-H22 — Controlled Staging Posted-Ledger Report Switch Dry Run**

H21 does not start H22.  H22 begins only after this PR is merged, deployed to
Cloud Run, and live-verified via `/version` and `/health`.
