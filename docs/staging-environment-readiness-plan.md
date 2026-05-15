# Bridge Hub — Staging Environment Readiness Plan

## 1. Purpose

Task 11C-H20 defines the readiness requirements for a staging/non-production
environment before enabling `POSTED_LEDGER_REPORTS_ENABLED` outside unit tests
and before any future controlled production report migration.

**H20 is docs and contract tests only.**

- H20 does not create staging infrastructure.
- H20 does not change production runtime behavior.
- H20 does not enable any feature flag.
- H20 does not execute SQL or migrations.
- H20 does not touch production DB or Cloud Run DB.
- H20 does not activate Balance.ge.
- H20 does not change credentials, connector behavior, or infrastructure.

---

## 2. Background / H1–H19 Chain

| Task | Description |
|---|---|
| H1  | Found report ledger integrity risks — `journal_drafts` includes unposted entries |
| H2  | Defined posted journal entries schema contract |
| H3  | Defined safe schema migration plan |
| H4  | Created SQL migration contract; migration not executed |
| H5  | Defined posting service ledger write contract |
| H6  | Added posting ledger write mock tests |
| H7  | Defined reports posted-ledger read contract |
| H8  | Added report query mock tests |
| H9  | Defined reversal/correction contract |
| H10 | Defined evidence/audit export linkage (`evidence_bundle_id`, `audit_event_id`) |
| H11 | Defined controlled local/test migration execution plan |
| H12 | Attempted local/test migration execution; blocked (disposable PostgreSQL unavailable) |
| H13 | Defined runtime report migration plan with feature flag gate |
| H14 | Added report service query mock tests |
| H15 | Added feature-flagged posted-ledger path; production default OFF |
| H16 | Verified posted-ledger behavior with local/test fixture data |
| H17 | Verified UI/API drill-down contracts end-to-end |
| H18 | Defined controlled non-production runtime switch and production guard |
| H19 | Defined production migration approval plan |
| H20 | Defines staging environment readiness only (this document) |

---

## 3. Staging Non-Action Statement

H20 takes no action.  The following constraints are absolute:

- No staging Cloud Run service is created in H20.
- H20 does not create staging infrastructure.
- No Cloud Run service is changed.
- No Cloud Run env var changes.
- No DB is created or connected.
- No SQL execution.
- No migration execution.
- No Balance.ge activation.
- No credentials changed.
- No connector behavior changed.
- No infrastructure changed.
- No production DB connection.
- No Cloud Run DB connection.
- No feature flag is enabled anywhere in H20.
- `POSTED_LEDGER_REPORTS_ENABLED` remains OFF in all environments during H20.
- H20 does not start H21.

---

## 4. Required Staging Environment Components

A compliant staging environment for testing `POSTED_LEDGER_REPORTS_ENABLED` must
include all of the following before any non-production switch is attempted:

| Component | Requirement |
|---|---|
| Staging Cloud Run service | Separate Cloud Run service or equivalent non-production runtime — must not be the production service |
| Staging database | Separate staging DB or disposable test DB — must not be the production database |
| Staging tenant/test data | Synthetic or approved anonymized data only — no production customer rows |
| Staging secrets namespace | Separate secrets — no production credentials reused unless explicitly approved by security |
| Staging service account | Separate GCP service account with non-production IAM roles only |
| Isolated logs/monitoring | Staging logs labelled with `ENVIRONMENT=staging` or equivalent label |
| Environment marker | `ENVIRONMENT=staging` or equivalent set on staging Cloud Run service |
| Feature flag allowance | `POSTED_LEDGER_REPORTS_ENABLED` allowed only after explicit approval in staging |
| Balance.ge mode | Balance.ge must remain `demo_mode` in staging unless separately approved |
| ERP connector mode | No live ERP activation in staging unless separately approved |

---

## 5. Environment Isolation Requirements

The staging environment must satisfy all of the following isolation requirements:

- Staging must not share production DB — completely separate database instance required
- Staging must not share production write credentials — separate service account and secrets
- Staging must not post to live ERP/Balance.ge — connector remains `demo_mode`
- Staging must not send real customer notifications — email/messaging disabled or sandboxed
- Staging must not expose raw secrets in logs, `/health`, or report responses
- Staging test data must be synthetic or approved anonymized data — no real customer financial rows
- Tenant boundaries must be preserved — cross-tenant access forbidden even in staging
- RBAC behavior must match production expectations — same permission map applied
- Staging environment must be clearly labelled to prevent accidental production action

---

## 6. Feature Flag Readiness

Rules for `POSTED_LEDGER_REPORTS_ENABLED` in staging and all environments:

| Rule | Detail |
|---|---|
| Default | `POSTED_LEDGER_REPORTS_ENABLED` default OFF — unset equals disabled |
| Staging | Staging can enable only with explicit approval and documented test plan |
| Production | Production remains OFF at all times during H20 and until H19 approval gates satisfied |
| Unknown environment | Fail-closed — any unrecognised environment name treated as production-safe |
| Health/version checks | `/version` and `/health` checked before and after flag enablement |
| Rollback | Rollback by setting `POSTED_LEDGER_REPORTS_ENABLED=""` — legacy path resumes in one restart |
| No silent fallback | `_assert_no_silent_fallback` enforced — `journal_drafts` must never appear in posted-ledger queries |
| Fail-closed on unavailable tables | If `journal_entry_headers` or `journal_entry_lines` unavailable → `POSTED_LEDGER_UNAVAILABLE` error; no silent fallback |
| Truthy values | `"1"`, `"true"`, `"True"`, `"TRUE"`, `"yes"`, `"Yes"`, `"YES"` |

---

## 7. Staging Database Readiness

Before enabling `POSTED_LEDGER_REPORTS_ENABLED` in staging:

- Disposable/local/staging DB required — no production database connection
- Schema migration verified before switch — `journal_entry_headers` and `journal_entry_lines` present
- `journal_entry_headers` columns verified: `id`, `tenant_id`, `status`, `reversal_of_id`, `correction_of_id`, `posting_log_id`, `source_draft_id`, `evidence_bundle_id`
- `journal_entry_lines` columns verified: `id`, `journal_entry_id`, `tenant_id`, `account_code`, `debit`, `credit`, `ledger_line_id`
- Indexes and constraints verified — no missing FK/unique constraints
- `tenant_id` populated on every row
- Status rules verified — `posted`, `correction`, `reversed`, `voided` values present
- Evidence/posting/source links verified — `evidence_bundle_id`, `posting_log_id`, `source_draft_id` populated where applicable
- Rollback does not require dropping `journal_entry_headers` or `journal_entry_lines` — flag controls query path only
- PITR/backup expectations: if persistent staging DB exists, daily PITR enabled before testing

---

## 8. Test Data Readiness

The staging DB must contain sufficient test data before any feature flag switch:

- Posted income/expense/asset/liability/equity entries across at least two test tenants
- Correction/reversal chains — at least one `correction_of_id` link and one `reversal_of_id` link per tenant
- VAT/tax lines — at least one entry with VAT-relevant account codes
- Cash/bank lines — cashflow classification verified
- Payroll lines — payroll account codes present
- Counterparty/document links — `counterparty_id` and `document_id` populated on at least one entry per tenant
- `evidence_bundle_id`, `posting_log_id`, `source_draft_id` populated on posted entries
- Multi-tenant negative tests — rows from tenant A must not appear in tenant B reports
- Forbidden non-posted states excluded — no `draft`, `approved`, `auto_approved`, `simulated_success`, `mock_posting`, `dry_run` entries in posted-ledger report results

---

## 9. Report Verification Checklist

Each of the 11 official report types must be verified in staging before production approval.
For each report:

- Tenant filter: result contains only rows for the requested `tenant_id`
- Period/date filter: result respects the requested date range
- Old-vs-new comparison: legacy (`journal_drafts`) result compared to posted-ledger result; variance documented
- Drill-down check: `ledger_line_id` → `journal_entry_id` → `source_draft_id` → `posting_log_id` → `evidence_bundle_id`
- Evidence/audit check: `audit_event_id` accessible for all posted entries
- No raw secrets: `api_key`, `password`, `token`, `secret` absent from all response payloads

| # | Report Type |
|---|---|
| 1  | Trial Balance |
| 2  | Profit & Loss Summary |
| 3  | Profit & Loss Detail |
| 4  | Balance Sheet Summary |
| 5  | Balance Sheet Detail |
| 6  | VAT Register |
| 7  | Account Ledger |
| 8  | Counterparty Ledger |
| 9  | Payroll Ledger |
| 10 | Journal Entries List |
| 11 | Cashflow |

---

## 10. Security / Access Readiness

| Requirement | Detail |
|---|---|
| Staging auth/RBAC enabled | `require_permission` enforced on all report endpoints in staging |
| 401/403 behavior verified | Unauthenticated/unauthorised requests blocked on all protected endpoints |
| No cross-tenant access | `tenant_id` mandatory; cross-tenant rows filtered before any report response |
| Evidence bundle access scoped | `evidence_bundle_id` links accessible only to the owning `tenant_id` |
| Posting log access scoped | `posting_log_id` links accessible only to the owning `tenant_id` |
| Audit trail access scoped | `audit_event_id` links accessible only to the owning `tenant_id` |
| Secrets not in `/health` | No raw API keys, passwords, or tokens in `/health` response |
| No production secrets in staging logs | Staging service account must not log or expose production credentials |
| No live connector credentials | Balance.ge and ERP connectors remain `demo_mode` unless separately approved |

---

## 11. Monitoring / Observability Readiness

Monitoring must be configured before any staging flag switch:

| Signal | Requirement |
|---|---|
| `/version` check | Confirm staging SHA matches expected commit before and after switch |
| `/health` check | Confirm 200 and feature flag state visible in health response |
| Feature flag state | `POSTED_LEDGER_REPORTS_ENABLED` visible in `/health` env_vars check |
| Error rate | Baseline error rate recorded; alert if > 2× baseline post-switch |
| Latency | Report endpoint latency (p95) recorded; alert if > 2× baseline |
| `POSTED_LEDGER_UNAVAILABLE` | Any occurrence triggers immediate investigation/rollback in staging |
| Report discrepancy tracking | Old-vs-new comparison result logged and reviewed |
| Auth failures | 401/403 rate monitored for unexpected spikes |
| Audit/evidence drill-down errors | Any drill-down chain error logged and investigated |
| Rollback verification | After rollback: `/health` confirms flag is absent; legacy path resumes |
| Staging log labels | All staging logs carry `environment=staging` label; never mixed with production |

---

## 12. Rollback Readiness

Rollback in staging is non-destructive:

1. Unset `POSTED_LEDGER_REPORTS_ENABLED` — set to `""` or remove from staging env vars.
2. Restart the staging service — legacy `journal_drafts` path resumes in one cold start.
3. Confirm via `/health` that `POSTED_LEDGER_REPORTS_ENABLED` is absent or `false`.
4. Do not drop `journal_entry_headers` or `journal_entry_lines` tables.
5. Preserve all audit logs, evidence bundles, and posting logs.
6. Rollback owner: the engineer who enabled the staging flag.
7. Rollback trigger conditions: any `POSTED_LEDGER_UNAVAILABLE` event, any report discrepancy not explained, any tenant isolation violation, any unexpected 5xx spike.
8. Post-rollback smoke checks: run targeted contract tests; confirm report totals match pre-switch state.

**Non-destructive guarantee:** no schema change required for rollback — the feature flag controls only the query path.

---

## 13. Go / No-Go Checklist

Before enabling `POSTED_LEDGER_REPORTS_ENABLED` in staging:

- [ ] Staging environment isolated from production (separate Cloud Run, DB, secrets)
- [ ] Staging DB ready — `journal_entry_headers` and `journal_entry_lines` present and validated
- [ ] Staging secrets isolated — no production credentials in staging service account
- [ ] Synthetic/anonymized test data loaded for at least two tenants
- [ ] Migrations verified in staging/local — schema validated before switch
- [ ] Old-vs-new report comparison completed for all 11 report types
- [ ] All targeted contract tests green (H1–H20 suite)
- [ ] Monitoring ready — staging dashboard configured, alerts set
- [ ] Rollback tested and confirmed — unset flag restores legacy path in one restart
- [ ] Security/RBAC verified — 401/403 behavior confirmed in staging
- [ ] Owner sign-off: engineering lead and QA lead signed off
- [ ] Change window for staging switch approved and communicated

---

## 14. Staging Readiness Gaps

If the staging environment does not yet exist, the following must be resolved before
any non-production flag switch:

- **Staging Cloud Run service does not exist** → it must be created in a future infrastructure task before H21 can proceed
- **Staging database does not exist** → it must be created in a future DB readiness task; H20 does not perform this action
- **Staging secrets do not exist** → a separate secrets namespace must be provisioned before staging switch
- **Safe test data does not exist** → synthetic/anonymized test data must be prepared before any staging switch; H20 does not create this data
- **Schema migration not run in staging** → local/staging migration must be verified before flag enablement; H20 does not execute migrations
- H20 does not perform any of the above actions — all are deferred to future tasks

---

## 15. Non-Goals for H20

This task does **not**:

- Create staging Cloud Run service or any staging infrastructure
- Execute any production switch or staging switch
- Enable any feature flag
- Execute any SQL
- Run any migrations
- Connect to any DB
- Touch production DB or Cloud Run DB
- Change any Cloud Run environment variables
- Activate Balance.ge or any ERP connector
- Change any connector behavior
- Change any credentials
- Change any infrastructure
- Change any runtime code
- Change any UI or static files
- Change posting behavior
- Change approval logic
- Start H21

---

## 16. Next Task

Only after PR merge, deploy, and live verification:

**11C-H21 — Staging Infrastructure / Test Data Readiness Decision**

OR, if staging infrastructure already exists:

**11C-H21 — Controlled Staging Posted-Ledger Report Switch Dry Run**

H20 does not start H21.  H21 begins only after this PR is merged, deployed to
Cloud Run, and live-verified via `/version` and `/health`.
