# Bridge Hub — Production Report Migration Approval Plan

## 1. Purpose

Task 11C-H19 defines the formal approval plan and readiness checklist for the
future production migration from `journal_drafts`-based financial reports to the
`journal_entry_headers` / `journal_entry_lines` posted-ledger report path.

**This document is a planning artifact only.**  No production switch occurs in H19.
No feature flag is enabled in production.  No DB is accessed.  No Cloud Run
configuration is changed.  All verification in this task is documentation and
contract-test only.

---

## 2. Safety Scope

| Constraint | Status |
|---|---|
| Production feature flag (`POSTED_LEDGER_REPORTS_ENABLED`) remains OFF | required |
| No production Cloud Run config changes | required |
| No production DB access | required |
| No Cloud Run DB access | required |
| No SQL execution | required |
| No migration execution | required |
| No Balance.ge activation | required |
| No credentials changed | required |
| No connector behavior changed | required |
| No infrastructure changed | required |
| No posting behavior changed | required |
| No approval logic changed | required |
| No UI/static files changed | required |

---

## 3. Production Non-Action Statement

H19 does **not** execute the production migration.  The tasks H1–H18 collectively
establish the full safety evidence base.  H19 documents what must be true before
any authorised approver may grant production enablement.

The actual production switch (setting `POSTED_LEDGER_REPORTS_ENABLED=1` on the
live Cloud Run service) is deferred to a future task that has not been assigned
a task identifier yet and must not be started without the explicit go-ahead
documented in Section 7 of this plan.

---

## 4. H1–H18 Completion Chain

The following tasks must all be merged and live-verified before production approval
may be considered:

| Task | Description | Status |
|---|---|---|
| H1  | posted-ledger schema design | required |
| H2  | journal_entry_headers DDL | required |
| H3  | journal_entry_lines DDL | required |
| H4  | posting service integration | required |
| H5  | ERP connector safety | required |
| H6  | tenant isolation contract | required |
| H7  | RBAC permission map | required |
| H8  | audit log middleware | required |
| H9  | approval flow contract | required |
| H10 | period lock contract | required |
| H11 | fail-closed error contract | required |
| H12 | status filter contract | required |
| H13 | reversal/correction chain | required |
| H14 | evidence bundle linkage | required |
| H15 | feature flag gate | required |
| H16 | fixture verification | required |
| H17 | UI/API drill-down contract | required |
| H18 | controlled nonprod runtime switch | required |

All 18 tasks above must have a merged PR and a confirmed live SHA before the
production approval gate in Section 7 is opened.

---

## 5. Report Types in Scope

The following 11 official financial report types are included in the production
migration scope.  All 11 must be verified on the posted-ledger path before the
go/no-go decision:

| # | Report Type | Key Tables |
|---|---|---|
| 1  | profit_and_loss | journal_entry_headers, journal_entry_lines |
| 2  | balance_sheet | journal_entry_headers, journal_entry_lines |
| 3  | cash_flow | journal_entry_headers, journal_entry_lines |
| 4  | trial_balance | journal_entry_headers, journal_entry_lines |
| 5  | accounts_payable_aging | journal_entry_headers, journal_entry_lines |
| 6  | accounts_receivable_aging | journal_entry_headers, journal_entry_lines |
| 7  | general_ledger | journal_entry_headers, journal_entry_lines |
| 8  | tax_summary | journal_entry_headers, journal_entry_lines |
| 9  | payroll_summary | journal_entry_headers, journal_entry_lines |
| 10 | budget_vs_actual | journal_entry_headers, journal_entry_lines |
| 11 | audit_trail | journal_entry_headers, journal_entry_lines |

---

## 6. Old vs New Report Path Comparison

| Property | Legacy path (`journal_drafts`) | Posted-ledger path |
|---|---|---|
| Data source | `journal_drafts` table | `journal_entry_headers` + `journal_entry_lines` |
| Entry status | all statuses (including draft) | `STANDARD_NET_STATUSES` only: `posted`, `correction` |
| Reversed entries | included in totals | excluded from net totals |
| `tenant_id` enforcement | per-query filter | strict; `ValueError` on empty |
| Fail-closed on missing tables | no (fallback behaviour) | yes → `POSTED_LEDGER_UNAVAILABLE` |
| Drill-down chain | not available | full chain: `ledger_line_id` → `journal_entry_id` → `source_draft_id` → `posting_log_id` → `evidence_bundle_id` |
| Response source tag | absent | `data.source == "posted_ledger"` |
| Audit evidence link | absent | `evidence_bundle_id` (nullable) + `audit_event_id` |
| ACCA/IFRS compliance | partial | full (`STANDARD_NET_STATUSES` enforced) |
| Rollback path | N/A (is the legacy path) | unset flag → legacy path resumes immediately |

---

## 7. Approval Gates

All eight gates below must be satisfied before any authorised approver may sign
off on production enablement:

| Gate | Description | Approver |
|---|---|---|
| G1 | H1–H18 all merged and live-verified | Engineering Lead |
| G2 | Non-production staging test completed with real non-prod DB | Engineering Lead + QA |
| G3 | All 11 report types verified on posted-ledger path in staging | QA Lead |
| G4 | No `journal_drafts` references in any report query executed in staging | Engineering Lead |
| G5 | Fail-closed behavior confirmed in staging: `POSTED_LEDGER_UNAVAILABLE` raised when tables absent | QA Lead |
| G6 | Rollback test passed: unset flag → legacy path resumes within one restart | Engineering Lead |
| G7 | Monitoring plan executed: no unexpected errors in non-prod logs for ≥ 24 hours post-switch | On-call Engineer |
| G8 | Final production approval sign-off document completed and countersigned | CTO or delegated approver |

---

## 8. Go / No-Go Checklist

Before enabling `POSTED_LEDGER_REPORTS_ENABLED` on the production Cloud Run service:

- [ ] All 8 approval gates (G1–G8) satisfied and documented
- [ ] Confirmed environment is `production` Cloud Run service, not a test revision
- [ ] Non-prod staging run completed with test data only
- [ ] `journal_entry_headers` and `journal_entry_lines` tables present in production DB
- [ ] All 11 report types return correct totals in staging
- [ ] Reversal/correction exclusion confirmed: `reversed` entries absent from net totals
- [ ] Tenant isolation spot-checked: cross-tenant rows absent from all report responses
- [ ] Drill-down chain verified end-to-end in staging (report row → audit evidence)
- [ ] Fail-closed behavior explicitly retested in staging immediately before production switch
- [ ] Rollback plan rehearsed and confirmed working (Section 11)
- [ ] Monitoring dashboard active and alerts configured (Section 10)
- [ ] On-call engineer aware and reachable during switch window
- [ ] No Balance.ge production calls during switch window
- [ ] No connector activation during switch window
- [ ] No credentials changed during switch window
- [ ] Switch window communicated to all relevant stakeholders

---

## 9. Production Enablement Command (For Reference Only — Do Not Execute in H19)

The following command is documented here for reference.  It must not be executed
as part of H19 or any task before all approval gates are satisfied:

```
# REFERENCE ONLY — DO NOT EXECUTE WITHOUT FULL APPROVAL
gcloud run services update fastapi-run \
  --region europe-west1 \
  --update-env-vars POSTED_LEDGER_REPORTS_ENABLED=1
```

Any execution of this command without documented gate sign-off is a protocol
violation and must be reverted immediately.

---

## 10. Monitoring Plan

After production enablement (future task, not H19):

| Signal | Threshold | Action |
|---|---|---|
| `POSTED_LEDGER_UNAVAILABLE` error rate | > 0 in first 10 minutes | Immediate rollback |
| Report endpoint 5xx rate | > baseline | Rollback + incident |
| `journal_drafts` query log entries from report path | any | Immediate rollback |
| Response time p95 on `/reports/*` | > 2× pre-switch baseline | Investigate; rollback if not resolved in 30 min |
| Tenant isolation violations in logs | any | Immediate rollback + security incident |
| Missing `data.source == "posted_ledger"` tag in report responses | any | Rollback |

Monitoring window: minimum 24 hours of clean logs before considering the switch stable.

---

## 11. Rollback Plan

If production enablement causes any unexpected behaviour:

1. Unset the flag immediately:
   ```
   gcloud run services update fastapi-run \
     --region europe-west1 \
     --update-env-vars POSTED_LEDGER_REPORTS_ENABLED=""
   ```
2. Restart the service — legacy `journal_drafts` path resumes within one cold start.
3. Confirm via `/health` that `POSTED_LEDGER_REPORTS_ENABLED` is absent or `false`.
4. File an incident report with:
   - Time of enablement
   - Time of rollback
   - Observed error
   - Tenant(s) affected (if any)
5. No DB migration or schema change required — the flag controls only the query path.
6. Do not re-enable without a new approval cycle starting from Gate G5.

---

## 12. Security and Compliance Requirements

| Requirement | Detail |
|---|---|
| Tenant isolation | All report queries must carry `WHERE tenant_id = $N`; verified in H6 |
| No raw secrets in payloads | `api_key`, `password`, `token`, `secret` forbidden in all report responses; verified in H17 |
| RBAC enforcement | `require_permission` must be called on all report endpoints; verified in H7 |
| ACCA/IFRS status filter | Only `STANDARD_NET_STATUSES` in net totals; verified in H12 |
| Audit trail | `evidence_bundle_id` linkage verified in H14 and H17 |
| No silent fallback | `_assert_no_silent_fallback` enforced; verified in H16 and H17 |

---

## 13. Non-goals

This task does **not**:

- Switch production to posted-ledger reports
- Access production DB
- Execute any DB migration
- Activate Balance.ge or any ERP connector
- Change posting service logic
- Change approval service logic
- Implement any UI/static pages
- Run staging or deploy a new Cloud Run revision
- Start any post-H19 production-enabling task

---

## 14. Verification Plan

- Documentation completeness contract tests only — no DB, no network, no Cloud Run mutation.
- All 29 contract tests run locally in-memory, no external dependencies.
- Approval gate completeness verified by test enumeration.
- Report type coverage verified by test enumeration.
- Go/no-go checklist item count verified by test.
- H1–H18 chain completeness verified by test enumeration.

---

## 15. Test Results

| Suite | Command | Result |
|---|---|---|
| H19 targeted | `pytest tests/unit/test_production_report_migration_approval_plan_contract.py -v` | **29 passed** |
| Full unit suite | `pytest tests/unit/` | **3852 passed, 2 skipped** |

All runs: 0 failed, 5 deprecation warnings (SwigPy — unrelated to project code).

---

## 16. Next Step

After all approval gates (G1–G8) are satisfied and sign-off documentation is
complete, a new production-enabling task will be assigned.  That task will:

- Set `POSTED_LEDGER_REPORTS_ENABLED=1` on the production Cloud Run service
- Confirm via `/health` that the flag is active
- Monitor for the 24-hour clean-log window
- Close out the production migration
