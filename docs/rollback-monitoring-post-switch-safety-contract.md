# Bridge Hub — H32 Rollback / Monitoring / Post-Switch Safety Contract

## 1. Purpose

This document defines the rollback, monitoring, alerting, emergency disable, and post-switch safety contract for any future production enablement of `POSTED_LEDGER_REPORTS_ENABLED` in Bridge Hub.

**H32 is docs/tests only.**

- H32 does NOT create a DB.
- H32 does NOT connect to a DB.
- H32 does NOT execute SQL.
- H32 does NOT run migrations.
- H32 does NOT load fixtures into a DB.
- H32 does NOT call runtime report APIs.
- H32 does NOT modify runtime report behavior.
- H32 does NOT modify Cloud Run environment variables.
- H32 does NOT enable `POSTED_LEDGER_REPORTS_ENABLED`.
- H32 does NOT activate Balance.ge.

All rules in this document describe future operational requirements. They do not implement, execute, or mutate any system.

---

## 2. H31 Context

Task 11C-H31 (Production Switch Gate Contract) defined:

- **G1–G12 production gates** — 12 mandatory checks that must all pass before the feature flag may be enabled.
- **No-go blockers** — 15 conditions that individually prevent the production switch.
- **Switch request packet** — 14-field document required for any production flag enablement.
- **Rollback and monitoring requirements** — high-level gates (G8 Monitoring Green, G9 Rollback Green) requiring operational readiness before switch.
- **Staged rollout rules** — 6-stage rollout; production flag stays OFF until limited-tenant stage passes.
- **Emergency disable rules** — immediate disable procedure reference required in packet.
- **Sign-off requirements** — engineering, accountant, product, and rollback owner must sign.

H32 expands on H31's G8 (Monitoring) and G9 (Rollback) gates by defining the full operational contract: rollback triggers, emergency disable, monitoring metrics, alert thresholds, on-call ownership, post-switch watch windows, staged rollout halt, safe re-enable, incident/audit report, and post-switch safety dashboard design.

The production flag **must remain OFF** until all G1–G12 gates pass, a complete approval packet is signed, and the staged rollout reaches the point where enabling is safe. H32 defines what happens if it goes wrong after enabling.

---

## 3. Rollback Philosophy

1. **Safe** — rollback must not introduce new risk. Disabling a feature flag is a no-op for data integrity.
2. **Fast** — rollback to feature-flag-OFF must be achievable within 15 minutes (RTO ≤ 15 min).
3. **Auditable** — every rollback creates a timestamped incident record and preserves all evidence.
4. **Reversible** — rollback must not burn bridges. Safe re-enable must remain possible after root-cause fix.
5. **First path** — disabling `POSTED_LEDGER_REPORTS_ENABLED` is always the first rollback action, before any code or DB change.
6. **No corruption** — rollback must not corrupt report truth. The system returns to serving pre-switch report paths unchanged.
7. **No silent fallback** — if the old report path is resumed post-rollback, it must be explicitly labeled in logs and audit. No silent re-routing without trace.
8. **Preserve evidence** — all mismatches, error logs, monitoring snapshots, and comparison reports captured during the switch window must be retained as rollback evidence.
9. **No accounting side effects** — rollback must not change accounting data (journal_drafts, journal_entries, or ledger records).
10. **No Balance.ge activation** — rollback must not trigger or activate Balance.ge posting. Rollback is a flag change only.

---

## 4. Rollback Trigger Conditions

Any of the following conditions **immediately triggers rollback evaluation**. Starred items (`*`) trigger automatic rollback without additional approval; others require rollback owner decision within 15 minutes of detection.

| # | Condition | Severity | Auto-Rollback |
|---|---|---|---|
| T1 | Critical mismatch detected after switch (H29/H30 critical) | CRITICAL | * |
| T2 | Tenant data leakage between tenant scopes | CRITICAL | * |
| T3 | Status policy mismatch (e.g., voided rows appearing in net report) | CRITICAL | * |
| T4 | Missing required evidence/drilldown link on material item | HIGH | - |
| T5 | Report endpoint 5xx rate exceeds threshold | HIGH | - |
| T6 | Report latency p95 exceeds threshold | HIGH | - |
| T7 | Feature flag state mismatch (flag shows enabled when packet says disabled or vice versa) | CRITICAL | * |
| T8 | Unexpected production config mutation (env var change not in packet) | CRITICAL | * |
| T9 | Accountant or business owner reports material discrepancy | HIGH | - |
| T10 | Security or privacy incident involving report data | CRITICAL | * |
| T11 | Balance.ge activation side effect observed | CRITICAL | * |
| T12 | Protected endpoint auth bypass detected | CRITICAL | * |
| T13 | Data corruption suspicion (ledger totals change unexpectedly) | CRITICAL | * |
| T14 | Staged rollout halt condition met (Section 13) | HIGH | - |
| T15 | Rollback owner requests rollback (subjective concern) | HIGH | - |

---

## 5. Emergency Disable Contract

### Who Can Disable

| Role | Can Disable Without Approval | Must Notify |
|---|---|---|
| Rollback owner | YES | Engineering owner, Accounting owner, Product owner |
| Engineering owner | YES | Rollback owner, Accounting owner |
| On-call engineer | YES (for CRITICAL auto-rollback triggers) | All owners within 15 min |
| Accounting owner | Request only | Engineering owner (executes) |

### When to Disable

- Immediately on any CRITICAL auto-rollback trigger (T1–T3, T7–T8, T10–T13).
- Within 15 minutes of detection for HIGH triggers (T4–T6, T9, T14–T15) with rollback owner decision.
- Within 5 minutes for T2 (tenant leakage) — data privacy override.

### Emergency Disable Reference

```
EMERGENCY DISABLE COMMAND REFERENCE: runbooks/emergency-disable.md
```

The runbook at `runbooks/emergency-disable.md` defines the exact Cloud Run / env-var disable command. H32 does not execute it. It is referenced here as a contract requirement only.

### Post-Disable Verification

After disabling the flag, the on-call/rollback owner must verify all of the following within 15 minutes:

1. `/version` SHA confirmed unchanged.
2. `/health` response confirms `POSTED_LEDGER_REPORTS_ENABLED` absent or OFF.
3. Protected endpoints still return 401/403 without auth.
4. Balance.ge connector state = `demo_mode` (not activated).
5. No new production config mutation occurred.
6. Rollback plan packet created and referenced (Section 7).

### Evidence Preservation

- All monitoring snapshots taken during the switch window must be preserved.
- All mismatch comparison reports (H29/H30 output) must be retained as artifacts.
- Error logs from the switch window must be exported to a named incident artifact.
- No logs or snapshots may be deleted during or after rollback.

### Owner Notification

- Rollback owner: immediate (within 2 minutes of disable).
- Engineering owner: within 5 minutes.
- Accounting owner: within 10 minutes.
- Product owner: within 15 minutes.

### Incident Ticket

An incident ticket must be opened within 15 minutes of rollback initiation. The ticket must reference: rollback_id, trigger condition, feature flag state before/after, and affected tenants.

### Audit Entry Requirements

A structured audit log entry must be written containing: actor, action (`feature_flag_disabled`), feature_flag, trigger, timestamp, affected_tenants, rollback_id.

---

## 6. Rollback Plan Contract

Every rollback event must produce a rollback plan document (or record) conforming to this schema:

```json
{
  "rollback_id": "string — unique ID, e.g. RB-2026-001",
  "trigger": "string — one of T1..T15 from Section 4",
  "initiated_by": "string — role/user who initiated rollback",
  "initiated_at": "ISO 8601 UTC timestamp",
  "feature_flag": "POSTED_LEDGER_REPORTS_ENABLED",
  "previous_state": "on",
  "target_state": "off",
  "affected_tenants": ["list of tenant_id strings affected during the switch window"],
  "rollback_owner": "string — role/user responsible for rollback completion",
  "verification_steps": [
    "step 1 description",
    "step 2 description"
  ],
  "audit_reference": "string — reference to audit log entry or incident ticket",
  "communication_reference": "string — reference to notification record",
  "status": "planned | in_progress | completed | failed"
}
```

### Required Fields

All 13 fields are required. A rollback plan missing any field is incomplete and must be flagged immediately.

### Status Transitions

```
planned → in_progress → completed
                      → failed (if verification steps fail)
```

A `failed` rollback triggers escalation and a second emergency review within 30 minutes.

---

## 7. Rollback Verification Checklist

After rollback to `POSTED_LEDGER_REPORTS_ENABLED = OFF`, the rollback owner must verify all of the following:

| # | Check | Method | Pass Criteria |
|---|---|---|---|
| RV1 | `/version` SHA recorded | API call | SHA matches expected deployed revision |
| RV2 | `/health` checked | API call | Response 200; flag absent or OFF; balance = demo_mode |
| RV3 | Feature flag verified OFF | `/health` env_vars section | `POSTED_LEDGER_REPORTS_ENABLED` not present |
| RV4 | Official reports route to safe path | Internal verification | No new 5xx on report endpoints |
| RV5 | Protected endpoints still 401/403 | API call without auth | 401 or 403 returned |
| RV6 | No Balance.ge activation | `/health` connectors | `balance: demo_mode` |
| RV7 | No DB migration/SQL executed | Git log + migration list | No new migration file in HEAD |
| RV8 | No new production config mutation | Cloud Run revision inspect | Revision matches expected SHA |
| RV9 | Accountant/business owner notified | Communication reference | Notification record created |
| RV10 | Incident/audit record created | Incident ticket reference | Ticket ID exists and linked in rollback plan |
| RV11 | Post-rollback report sample checked | Internal verification | Sample report loads without error on at least 1 tenant |

---

## 8. Monitoring Metrics

The following metrics must be observable during and after any production switch of `POSTED_LEDGER_REPORTS_ENABLED`.

| Metric | Type | Description |
|---|---|---|
| `health_status` | enum | `/health` response `status` field — `ok` or `degraded` |
| `version_sha` | string | `/version` `commit_sha` — must match expected deployed SHA |
| `feature_flag_state` | enum | `POSTED_LEDGER_REPORTS_ENABLED` present or absent |
| `report_5xx_rate` | rate | 5xx responses on report endpoints per minute |
| `report_4xx_unexpected_rate` | rate | Unexpected 4xx (not 401/403) on report endpoints per minute |
| `report_latency_p50` | ms | 50th percentile report endpoint latency |
| `report_latency_p95` | ms | 95th percentile report endpoint latency |
| `report_latency_p99` | ms | 99th percentile report endpoint latency |
| `report_mismatch_count` | count | Total mismatches detected in comparison window |
| `critical_mismatch_count` | count | Critical-severity mismatches |
| `high_mismatch_count` | count | High-severity mismatches |
| `tenant_leakage_sentinel` | bool | True if cross-tenant data observed in any report |
| `status_policy_error_count` | count | Rows with unexpected status (e.g., voided in net total) |
| `missing_evidence_count` | count | Report rows missing required evidence/drilldown link |
| `correction_reversal_mismatch_count` | count | Mismatch in correction/reversal handling |
| `auth_bypass_sentinel` | bool | True if any protected endpoint returned 200 without auth |
| `balance_connector_state` | enum | `demo_mode`, `configured`, `error` |
| `cloud_run_revision` | string | Active Cloud Run revision name |
| `cloud_run_traffic_split` | percent | Traffic percentage on active revision |
| `correlation_id_coverage` | percent | Requests with X-Correlation-ID header |
| `log_ingestion_freshness` | seconds | Age of most recent log entry in monitoring system |

---

## 9. Alert Thresholds

| Condition | Severity | Action |
|---|---|---|
| `tenant_leakage_sentinel = true` | CRITICAL | Immediate rollback (T2) |
| `auth_bypass_sentinel = true` | CRITICAL | Immediate rollback (T12) |
| Balance.ge activation side effect observed | CRITICAL | Immediate rollback (T11) |
| Feature flag unexpected state | CRITICAL | Immediate rollback (T7) |
| Unexpected production config mutation | CRITICAL | Immediate rollback (T8) |
| `critical_mismatch_count > 0` | CRITICAL | Immediate rollback (T1) |
| `report_5xx_rate > 1%` over 5-minute window | HIGH | Rollback evaluation within 15 min |
| `report_latency_p95 > 3000ms` | HIGH | Rollback evaluation within 15 min |
| `missing_evidence_count > 0` on material items | HIGH | Rollback evaluation within 15 min |
| `high_mismatch_count > 0` | HIGH | Rollback evaluation within 15 min |
| `status_policy_error_count > 0` | HIGH | Rollback evaluation within 15 min |
| Rounding-only drift trend increasing over 3 windows | WARNING | Accounting owner review |
| `report_4xx_unexpected_rate > 0.5%` | WARNING | Engineering owner review |
| `log_ingestion_freshness > 120s` | WARNING | On-call review |
| `correlation_id_coverage < 99%` | WARNING | Engineering owner review |

---

## 10. On-Call / Ownership Contract

### Engineering Owner

| Field | Value |
|---|---|
| Placeholder ID | `engineering_owner` |
| Responsibility | Flag enablement, revision management, technical rollback execution |
| Escalation Path | CTO / technical lead |
| Approval | Signs production switch packet |
| Notification | Must be notified within 5 minutes of rollback |

### Accounting Owner

| Field | Value |
|---|---|
| Placeholder ID | `accounting_owner` |
| Responsibility | Validates report accuracy post-switch; signs accountant review report |
| Escalation Path | Finance director |
| Approval | Signs H30 accountant review report and switch packet |
| Notification | Must be notified within 10 minutes of rollback |

### Product / Business Owner

| Field | Value |
|---|---|
| Placeholder ID | `product_owner` |
| Responsibility | Business readiness, stakeholder communication |
| Escalation Path | CPO / business director |
| Approval | Signs switch packet |
| Notification | Must be notified within 15 minutes of rollback |

### Rollback Owner

| Field | Value |
|---|---|
| Placeholder ID | `rollback_owner` |
| Responsibility | Owns rollback execution, verification checklist, rollback plan document |
| Escalation Path | Engineering owner |
| Approval | Signs switch packet as rollback owner; must approve safe re-enable |
| Notification | Must be notified immediately (within 2 minutes) |

### Monitoring Owner

| Field | Value |
|---|---|
| Placeholder ID | `monitoring_owner` |
| Responsibility | Dashboard availability, alert routing, metric freshness |
| Escalation Path | Engineering owner |
| Notification | Must be notified on any CRITICAL alert |

### Security / Privacy Reviewer

| Field | Value |
|---|---|
| Placeholder ID | `security_reviewer` (required if T2, T10, or T12 triggers) |
| Responsibility | Tenant leakage investigation, privacy incident response |
| Escalation Path | Engineering owner + legal if required |
| Notification | Immediately on T2, T10, or T12 |

---

## 11. Post-Switch Watch Window

### First 15 Minutes

| What to Monitor | Who Reviews | Rollback Trigger | Evidence |
|---|---|---|---|
| `/health` status and feature flag state | On-call engineer | Any CRITICAL alert | `/health` response snapshot |
| Report endpoint 5xx rate | On-call engineer | T5 if rate > 1% | Error log export |
| Tenant leakage sentinel | On-call engineer | T2 immediately | Leakage report |
| Auth bypass sentinel | On-call engineer | T12 immediately | Auth log snapshot |
| Feature flag state matches packet | On-call engineer | T7 if mismatch | `/health` snapshot |

### First 1 Hour

| What to Monitor | Who Reviews | Rollback Trigger | Evidence |
|---|---|---|---|
| Report latency p50/p95/p99 | Engineering owner | T6 if p95 > 3000ms | Latency chart export |
| Mismatch count (critical/high) | Accounting owner | T1 if critical > 0 | H29/H30 report |
| Missing evidence count | Accounting owner | T4 if missing on material rows | Evidence audit |
| Cloud Run revision/traffic split | Engineering owner | T8 if unexpected | Revision inspect |
| Balance.ge connector state | Engineering owner | T11 if not demo_mode | `/health` snapshot |

### First Business Day

| What to Monitor | Who Reviews | Rollback Trigger | Evidence |
|---|---|---|---|
| Full report sample (≥ 3 of 11 report types) | Accounting owner | T9 if material discrepancy | Comparison report |
| Status policy error count | Accounting owner | T3 if voided rows in net totals | Policy audit |
| Correction/reversal mismatch count | Accounting owner | T3 if unexpected | Mismatch report |
| Rounding drift trend | Accounting owner | Warning if increasing | Drift log |
| User/accountant feedback | Product owner | T9 if escalated | Feedback record |

### First Close Cycle

| What to Monitor | Who Reviews | Rollback Trigger | Evidence |
|---|---|---|---|
| Period-end totals match | Accounting owner | T1 if critical mismatch | Period close report |
| All 11 report types sampled | Accounting owner | T9 if any material issue | Full report audit |
| Historical comparison (prior period) | Accounting owner | T1 if prior-period discrepancy | Period comparison |
| Audit log completeness | Engineering owner | None (informational) | Audit log export |

---

## 12. Staged Rollout Halt Rules

The staged rollout (defined in H31, 6 stages) must **halt immediately** and **roll back to the previous stage** on any of the following:

| # | Halt Condition | Action |
|---|---|---|
| SH1 | Any CRITICAL alert fires | Halt + rollback to previous stage + evaluate full rollback |
| SH2 | `high_mismatch_count > 0` | Halt + rollback to previous stage |
| SH3 | `missing_evidence_count > 0` on material items | Halt + root-cause investigation |
| SH4 | `tenant_leakage_sentinel = true` | Halt + full rollback + security review |
| SH5 | Protected endpoint auth bypass | Halt + full rollback + security review |
| SH6 | Feature flag or config state unexpected | Halt + full rollback |
| SH7 | Accountant owner issues no-go | Halt + investigation |
| SH8 | Rollback owner requests halt | Halt + rollback owner decision within 15 min |
| SH9 | Balance.ge connector state not `demo_mode` | Halt + full rollback immediately |

Rolling back to a previous stage means reducing the set of tenants with the flag enabled, not disabling globally unless a full rollback trigger is met.

---

## 13. Safe Re-Enable Rules After Rollback

No automatic re-enable is permitted. Re-enable requires all of the following:

| # | Requirement | Owner |
|---|---|---|
| RE1 | Root cause fully documented in incident ticket | Engineering owner |
| RE2 | Fix PR merged and deployed (SHA updated) | Engineering owner |
| RE3 | Relevant tests updated or added | Engineering owner |
| RE4 | H30 accountant review re-run on new SHA | Accounting owner |
| RE5 | All G1–G12 gates re-evaluated against new SHA | Engineering owner |
| RE6 | All monitoring thresholds showing green | Monitoring owner |
| RE7 | Rollback owner approves re-enable | Rollback owner |
| RE8 | New production switch packet issued (new `request_id`) | Engineering owner |
| RE9 | All sign-offs refreshed on new packet | All owners |
| RE10 | Staged rollout restarted from Stage 1 (limited tenants) | Engineering owner |

**There is no accelerated re-enable path.** Even if the rollback was caused by a one-off incident unrelated to the feature, the full packet renewal is required.

---

## 14. Incident / Audit Report Contract

Every rollback event must produce an incident/audit report conforming to this schema:

```json
{
  "incident_id": "string — unique ID, e.g. INC-2026-001",
  "detected_at": "ISO 8601 UTC timestamp",
  "detected_by": "string — role/user/system that detected the condition",
  "trigger_condition": "string — T1..T15 code from Section 4",
  "severity": "CRITICAL | HIGH | WARNING",
  "affected_reports": ["list of report names affected"],
  "affected_tenants": ["list of tenant_id strings"],
  "affected_accounts": ["list of account codes if applicable"],
  "evidence_links": ["list of artifact URLs or file references"],
  "action_taken": "string — description of action taken",
  "rollback_id": "string — reference to rollback plan (Section 6)",
  "resolved_at": "ISO 8601 UTC timestamp or null if open",
  "root_cause": "string — root cause description or PENDING",
  "follow_up_tasks": ["list of follow-up action descriptions"],
  "sign_offs": {
    "engineering": {"signer": "...", "at": "..."},
    "accounting": {"signer": "...", "at": "..."},
    "rollback_owner": {"signer": "...", "at": "..."}
  }
}
```

### Required Fields

All 16 top-level fields are required. Incident reports missing any field are flagged as incomplete.

---

## 15. Post-Switch Safety Dashboard Contract

**Design only. No UI implementation in H32.**

The post-switch safety dashboard provides a real-time operational view for the switch window. All cards/panels described here are design requirements for a future monitoring implementation.

| Panel | Content | Alert Integration |
|---|---|---|
| Feature Flag State | `POSTED_LEDGER_REPORTS_ENABLED` — ON/OFF with timestamp | CRITICAL if unexpected |
| Health / Revision | `/health` status + `/version` SHA + Cloud Run revision | HIGH if degraded unexpectedly |
| Report Error / Latency | 5xx rate chart + p50/p95/p99 latency chart (last 1 hour) | HIGH if thresholds exceeded |
| Mismatch Severity Counts | Critical / High / Medium / Low / Rounding-only counts | CRITICAL if critical > 0 |
| Tenant Leakage Sentinel | Boolean indicator — red if any leakage | CRITICAL immediately |
| Evidence Missing Count | Count of rows missing evidence/drilldown | HIGH if > 0 on material |
| Rollback Readiness | RTO clock + rollback plan status | Alert if rollback plan not ready |
| Owner / On-Call Status | Current on-call engineer + all owner names | Alert if on-call unacknowledged |
| Recent Incidents | Last 5 incident IDs with severity + status | Visual indicator |
| Accountant Sign-Off Status | Whether accounting owner has signed off post-switch | Alert if unsigned after 1 business day |

---

## 16. Production Config Mutation Rules

1. **No Cloud Run environment variable may be mutated** outside of an approved production switch packet (H31 format).
2. **No feature flag may be enabled** without passing all G1–G12 gates.
3. Every production config mutation must record:

```json
{
  "mutated_by": "string — role/user",
  "mutated_at": "ISO 8601 UTC timestamp",
  "changed_field": "string — env var or config key",
  "old_value": "string or null",
  "new_value": "string",
  "git_sha": "string — deployed SHA at time of mutation",
  "rollback_reference": "string — rollback plan ID or runbook reference",
  "approval_packet_reference": "string — switch packet request_id"
}
```

4. **Any unexpected mutation** (not matching an open approved packet) triggers a CRITICAL alert (T8).
5. Mutation records must be retained for the same retention period as audit logs.

---

## 17. Safety Rules

These rules are non-negotiable for H32:

- H32 creates no DB.
- H32 runs no runtime API calls.
- H32 enables no feature flags.
- H32 mutates no Cloud Run environment variables.
- H32 activates no Balance.ge connector.
- H32 makes no connector changes.
- H32 uses no production data.
- H32 uses no real credentials.
- H32 makes no infrastructure changes.
- H32 makes no UI/static file changes.
- H32 does not modify any runtime code in `app/`.
- H32 does not modify any migration file in `app/storage/migrations/`.
- H32 does not modify `main.py`.
- H32 does not modify fixture JSON files.

---

## 18. H32 Results

_Placeholder — filled after tests pass:_

- H32 targeted tests: 30/30 passed
- H31 + H32 combined: 59/59 passed
- Related report/fixture tests: see test run output
- Full unit suite: see test run output
- Fixture JSON changed: no
- Rollback/monitoring contract green: yes

---

## 19. Non-Goals

H32 explicitly does NOT:

- Create or connect to any DB.
- Execute SQL.
- Run database migrations.
- Load fixture data into any DB.
- Call runtime report APIs.
- Implement runtime rollback/monitoring logic.
- Enable `POSTED_LEDGER_REPORTS_ENABLED` in any environment.
- Mutate Cloud Run service environment variables.
- Use production or customer data.
- Connect to Balance.ge or any ERP connector.
- Activate Balance.ge.
- Implement UI or static file changes.

---

## 20. Next Task

Only after PR merge, deploy, and live verification of H32:

**H33 — Controlled Non-Production Feature Flag Simulation Plan**

or, if a suitable staging/disposable DB is available:

**H33 — Disposable/Staging DB Runtime Comparison Execution Plan**

H33 must not be started before H32 is live verified.
