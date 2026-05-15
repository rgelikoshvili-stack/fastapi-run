# Bridge Hub — Production Report Migration Approval Plan

## 1. Purpose

Task 11C-H19 defines the formal production approval plan for eventually migrating
official financial reports from the legacy `journal_drafts`-derived behavior to
posted-ledger report mode using `journal_entry_headers` and `journal_entry_lines`.

**H19 is docs and contract tests only.**

- H19 does not enable the production feature flag.
- H19 does not change production runtime behavior.
- H19 does not execute SQL or migrations.
- H19 does not touch production DB or Cloud Run DB.
- H19 does not activate Balance.ge.
- H19 does not change credentials, connector behavior, or infrastructure.

---

## 2. Background / H1–H18 Chain

The following tasks collectively established the full safety evidence base for a
future production report migration:

| Task | Description |
|---|---|
| H1  | Found report ledger integrity risks — `journal_drafts` includes unposted entries |
| H2  | Defined posted journal entries schema contract (`journal_entry_headers`, `journal_entry_lines`) |
| H3  | Defined safe schema migration plan (SQL contract without execution) |
| H4  | Created SQL migration contract; migration not executed |
| H5  | Defined posting service ledger write contract for ERP connector dispatch |
| H6  | Added posting ledger write mock tests |
| H7  | Defined reports posted-ledger read contract |
| H8  | Added report query mock tests |
| H9  | Defined reversal/correction contract — `reversed` entries excluded from net totals |
| H10 | Defined evidence/audit export linkage (`evidence_bundle_id`, `audit_event_id`) |
| H11 | Defined controlled local/test migration execution plan |
| H12 | Attempted local/test migration execution; blocked when disposable PostgreSQL was unavailable |
| H13 | Defined runtime report migration plan with feature flag gate |
| H14 | Added report service query mock tests |
| H15 | Added feature-flagged runtime posted-ledger report path; production default OFF |
| H16 | Verified posted-ledger behavior with local/test fixture data only |
| H17 | Verified report UI/API drill-down contract end-to-end |
| H18 | Defined controlled non-production runtime switch and production guard |
| H19 | Defines production approval plan only (this document) |

---

## 3. Production Non-Action Statement

H19 takes no production action.  The following constraints are absolute:

- `POSTED_LEDGER_REPORTS_ENABLED` production flag remains OFF.
- No Cloud Run env var changes.
- No production DB connection.
- No Cloud Run DB connection.
- No SQL execution.
- No migration execution.
- No Balance.ge activation.
- No connector changes.
- No credential changes.
- No infrastructure changes.
- No posting or approval runtime changes.
- No UI/static file changes.
- H19 does not start H20.

---

## 4. Preconditions Before Any Future Production Switch

All of the following must be satisfied and documented before any authorised approver
may enable `POSTED_LEDGER_REPORTS_ENABLED` in production:

- [ ] Disposable local/test DB migration verified — schema applied in isolated environment, no production data
- [ ] Staging or non-production switch completed and verified — all 11 report types confirmed on posted-ledger path
- [ ] Posted ledger tables (`journal_entry_headers`, `journal_entry_lines`) present in production DB and validated
- [ ] Old vs new report comparison completed with zero critical discrepancies or approved exception list
- [ ] Accountant/business owner sign-off obtained and documented
- [ ] Technical owner sign-off documented
- [ ] Rollback plan approved — tested and rehearsed before production switch
- [ ] Monitoring plan approved — dashboard live, alerts configured
- [ ] Support/on-call plan approved — responsible engineer named and reachable during switch window
- [ ] Feature flag enablement window approved by engineering lead
- [ ] Production backup/PITR confirmed for the target period

---

## 5. Required Data / Ledger Preconditions

Before the production migration, the following data conditions must be verified:

- `journal_entry_headers` and `journal_entry_lines` present and populated for all active tenants
- `tenant_id` populated and enforced on every row
- `posted`, `correction`, `reversed`, and `voided` status rules validated
- `STANDARD_NET_STATUSES` (`posted`, `correction`) confirmed as the basis for official net totals
- No `journal_drafts` fallback in posted-ledger production mode
- `evidence_bundle_id`, `posting_log_id`, and `source_draft_id` linkage verified end-to-end
- Reversal/correction chains verified (`reversal_of_id`, `correction_of_id`)
- Cashflow classification verified for all applicable entries
- VAT/tax fields verified for completeness
- Period/date filters verified against expected reporting ranges

---

## 6. Old vs New Report Comparison Plan

For each of the 11 official report types, a side-by-side comparison must be run
against the same tenant, the same period/date range, and production-equivalent
test data before any production switch is approved.

| # | Report Type | Legacy Source | New Source | Comparison Required |
|---|---|---|---|---|
| 1  | Trial Balance | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 2  | Profit & Loss Summary | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 3  | Profit & Loss Detail | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 4  | Balance Sheet Summary | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 5  | Balance Sheet Detail | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 6  | VAT Register | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 7  | Account Ledger | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 8  | Counterparty Ledger | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 9  | Payroll Ledger | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 10 | Journal Entries List | journal_drafts | journal_entry_headers + journal_entry_lines | yes |
| 11 | Cashflow | journal_drafts | journal_entry_headers + journal_entry_lines | yes |

For each report type the comparison process must:

1. Capture legacy result (feature flag OFF) for the target tenant and period.
2. Capture posted-ledger result (feature flag ON in non-prod) for the same tenant and period.
3. Calculate variance for all numeric totals.
4. Document variance reason for any non-zero variance.
5. Obtain accountant review and sign-off on the comparison results.

---

## 7. Approval Gates

All eight gates below must be satisfied and countersigned before production enablement:

| Gate | Name | Description | Approver |
|---|---|---|---|
| G1 | Technical Readiness | H1–H18 all merged and live-verified; posted-ledger path deployed and tested in non-prod | Engineering Lead |
| G2 | Migration / Schema Readiness | Schema validated; `journal_entry_headers` and `journal_entry_lines` present; schema readiness confirmed | Engineering Lead |
| G3 | Report Comparison Readiness | Old vs new comparison completed for all 11 report types; variances documented | QA Lead |
| G4 | Accounting / Business Sign-off | Accountant review and business sign-off documented; exception list approved if needed | Business Owner |
| G5 | Security / Privacy Review | Tenant isolation, RBAC, no raw secrets, evidence bundle access scoped; privacy review complete | Security Lead |
| G6 | Rollback Readiness | Rollback rehearsed: feature flag OFF restores legacy path within one restart; verified | Engineering Lead |
| G7 | Production Change Approval | CTO or delegated approver sign-off; change window documented; stakeholders notified | CTO |
| G8 | Post-Switch Monitoring Approval | Monitoring dashboard live; alert thresholds set; on-call engineer assigned and reachable | On-call Lead |

---

## 8. Rollback Plan

The rollback is non-destructive: unsetting the feature flag immediately restores
the legacy `journal_drafts` report path.

**Steps:**

1. Unset `POSTED_LEDGER_REPORTS_ENABLED` (set to `""` or remove from Cloud Run env vars).
2. Restart the service — legacy path resumes within one cold start.
3. Confirm via `/health` that `POSTED_LEDGER_REPORTS_ENABLED` is absent or `false`.
4. Do not drop `journal_entry_headers` or `journal_entry_lines` tables.
5. Preserve all audit logs, evidence bundles, and posting logs.
6. File an incident report: time of enablement, time of rollback, observed error, affected tenants.
7. Rollback owner: the on-call engineer who initiated the production switch.
8. Rollback trigger conditions: any unexpected error, any `POSTED_LEDGER_UNAVAILABLE` event, any tenant isolation violation, any report discrepancy flagged by business users.
9. Rollback communication plan: notify engineering lead, business owner, and on-call immediately.
10. Post-rollback verification: run smoke checks on legacy report endpoints to confirm totals match pre-switch state.

**Non-destructive guarantee:** no DB migration or schema change is required for rollback.
The feature flag controls only the query path — unsetting it is sufficient.

---

## 9. Monitoring Plan

After any future production enablement (not in H19):

| Signal | Threshold | Action |
|---|---|---|
| `/version` SHA | Does not match expected commit | Investigate before proceeding |
| `/health` status | Not 200 | Immediate rollback |
| Feature flag state in `/health` | Absent or not enabled | Do not proceed |
| `POSTED_LEDGER_UNAVAILABLE` error rate | > 0 in first 10 minutes | Immediate rollback |
| Report endpoint latency (p95) | > 2× pre-switch baseline | Investigate; rollback if unresolved in 30 min |
| Error rate on `/reports/*` | > baseline | Rollback + incident |
| `journal_drafts` query log entries from report path | Any | Immediate rollback |
| Tenant isolation violations in logs | Any | Immediate rollback + security incident |
| Missing `data.source == "posted_ledger"` in responses | Any | Rollback |
| 401/403 auth behavior regression | Any | Rollback |
| Raw secrets exposure in any report payload | Any | Immediate rollback + security incident |
| Balance.ge remains unchanged | Any activation | Immediate rollback |
| Audit/evidence drilldown chain broken | Any | Rollback |

Monitoring window: minimum 24 hours of clean logs before considering the switch stable.

---

## 10. Security / Privacy Gates

| Requirement | Detail |
|---|---|
| `tenant_id` mandatory | All report queries carry `WHERE tenant_id = $N`; empty `tenant_id` raises `ValueError` |
| No raw secrets in payloads | `api_key`, `password`, `token`, `secret` forbidden in all report responses |
| RBAC enforcement | `require_permission` called on all report endpoints; verified in H7 |
| Tenant isolation | Cross-tenant rows filtered before response; verified in H6 and H17 |
| 401/403 behavior confirmed | Unauthenticated/unauthorised requests blocked on all drilldown endpoints |
| Evidence bundle access scoped | `evidence_bundle_id` links accessible only to the owning tenant |
| Posting log access scoped | `posting_log_id` links accessible only to the owning tenant |
| Audit trail access scoped | `audit_event_id` links accessible only to the owning tenant |
| No credentials changed | All connector credentials unchanged during and after switch |
| No connector behavior changed | Balance.ge remains `demo_mode` unless separately approved |
| Privacy review sign-off | Security lead confirms no PII exposure through drill-down payloads |

---

## 11. Go / No-Go Checklist

Before enabling `POSTED_LEDGER_REPORTS_ENABLED` on the production Cloud Run service:

- [ ] All 8 approval gates (G1–G8) satisfied and documented
- [ ] All unit tests green — 0 failures across full test suite
- [ ] Staging or non-production switch verified for all 11 report types
- [ ] Production backup/PITR confirmed for the target period
- [ ] All sign-offs collected (engineering, accounting/business, security, CTO)
- [ ] No critical unresolved discrepancies in old vs new comparison
- [ ] Rollback tested and confirmed — legacy path restored within one restart
- [ ] Monitoring ready — dashboard live, alerts configured, on-call assigned
- [ ] Support owner assigned and reachable during switch window
- [ ] Change window approved and communicated to stakeholders
- [ ] Feature flag change reviewed — no other flags toggled simultaneously
- [ ] Communication prepared — affected tenants notified if required

---

## 12. Production Switch Procedure — Future Only (Not Executed in H19)

The following procedure is documented for reference only.  It must not be executed
as part of H19.  Execution requires all approval gates to be satisfied.

1. Confirm commit SHA matches expected live SHA.
2. Confirm environment is production Cloud Run service.
3. Confirm production backup/PITR is current.
4. Enable flag only within the approved change window:
   ```
   # REFERENCE ONLY — DO NOT EXECUTE WITHOUT FULL APPROVAL
   gcloud run services update fastapi-run \
     --region europe-west1 \
     --update-env-vars POSTED_LEDGER_REPORTS_ENABLED=1
   ```
5. Run smoke checks immediately after enablement.
6. Run report comparison spot checks for at least two tenants.
7. Monitor for 24 hours; rollback if any threshold exceeded.

---

## 13. Post-Switch Verification — Future Only

After production enablement (future task, not H19):

- Confirm `/version` SHA matches expected commit.
- Confirm `/health` returns 200 and flag is reported as active.
- Confirm protected endpoints return 401/403 without valid auth.
- Confirm report endpoints return correct totals with valid auth.
- Run comparison spot checks for key tenants.
- Verify drill-down chain: report row → `ledger_line_id` → `journal_entry_id` → `source_draft_id` → `posting_log_id` → `evidence_bundle_id` → `audit_event_id`.
- Verify no raw secrets in any report response payload.
- Confirm Balance.ge has not been activated.

---

## 14. Non-Goals for H19

This task does **not**:

- Execute any production switch
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
- Start H20

---

## 15. Next Task

Only after PR merge, deploy, and live verification:

**11C-H20 — Staging Environment Readiness Plan**

OR, if the project does not have staging infrastructure yet:

**11C-H20 — Staging / Non-Production Switch Dry-Run Plan**

H19 does not start H20.  H20 begins only after this PR is merged, deployed to
Cloud Run, and live-verified via `/version` and `/health`.
