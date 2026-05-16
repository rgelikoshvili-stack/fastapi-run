# Bridge Hub — H31 Production Switch Gate Contract / Feature Flag Approval Checklist

## 1. Title

Bridge Hub — H31 Production Switch Gate Contract / Feature Flag Approval Checklist

Task: 11C-H31 — Production Switch Gate Contract / Feature Flag Approval Checklist
Branch: `codex/production-switch-gate-contract`
Starting SHA: `ec35a58cf4b4e9e8dc552a1a1d2d321f3a3c41c6` (H30 merge)

---

## 2. Purpose

H31 defines the final gate contract for any future production enablement of `POSTED_LEDGER_REPORTS_ENABLED`.
No production switch may proceed until every gate in this contract is satisfied and the approval packet
is complete.

H31 **does not** create a DB.
H31 **does not** connect to a DB.
H31 **does not** execute SQL.
H31 **does not** run migrations.
H31 **does not** load fixtures into any DB.
H31 **does not** call runtime report APIs.
H31 **does not** modify runtime report behavior.
H31 **does not** modify Cloud Run env vars.
H31 **does not** enable `POSTED_LEDGER_REPORTS_ENABLED`.
H31 **does not** activate Balance.ge.

All gate rules, checklists, and approval packet fields are defined as a local contract in this document
and validated in pure Python tests with no external dependencies.

---

## 3. H24–H30 Context

| Task | Contribution |
|---|---|
| H24 | Disposable DB dry-run blocked safely — local PostgreSQL unavailable at the time |
| H25 | Created synthetic fixture pack (docs/tests/JSON only) |
| H26 | Validated expected totals; corrected account_ledger.1010_bank gross totals |
| H27 | Defined old-vs-new snapshot comparison plan; 13 mismatch codes; G1–G10 approval gates |
| H28 | Defined snapshot normalizer contract; 10 normalization error codes; 4 helper signatures |
| H29 | Defined comparator/mismatch classifier contract; 20 mismatch codes; 4 comparison modes |
| H30 | Defined accountant review report contract; sign-off fields; audit metadata; production switch gate rules |
| H31 | Defines production switch gates G1–G12; approval checklist; no-go blockers; rollback/monitoring/emergency rules |

---

## 4. Feature Flag Identity

| Property | Value |
|---|---|
| Flag name | `POSTED_LEDGER_REPORTS_ENABLED` |
| Default | OFF / absent / false |
| Accepted true values | `1`, `true`, `yes` (case-insensitive) |
| Accepted false values | absent, `0`, `false`, `no`, empty string |
| Scope | Cloud Run service environment variable |
| Fail behavior | Fail-closed — if flag path fails at runtime, fall back to legacy path silently and log `WARNING` |
| Production default | Must remain OFF until all gates G1–G12 pass and approval packet is complete |
| Silent fallback allowed | Yes for runtime errors on new path; no for flag configuration errors |
| Explicit approval required | Yes — production switch request packet must be complete before any Cloud Run env var change |

---

## 5. Production Switch Non-Action Statement

H31 **does not** enable the flag.
H31 **does not** modify Cloud Run.
H31 **does not** touch production DB.
H31 **does not** run SQL.
H31 **does not** run migrations.
H31 **does not** use real customer data.
H31 **does not** call live report APIs.
H31 **does not** start the production switch.
H31 **does not** start H32.

---

## 6. Required Gate List

All 12 gates must be green before production switch is allowed. Gates are sequential — a failed gate
blocks all subsequent gates.

### G1 — Trust Foundation Green

| Check | Requirement |
|---|---|
| Credential masking | No raw `JWT_SECRET`, `DATABASE_URL`, `ANTHROPIC_API_KEY`, `BALANCE_API_KEY` in logs or responses |
| RBAC/tenant enforcement | All report endpoints require valid JWT; tenant_id isolation verified |
| Audit metadata | Every mutating request logged with `correlation_id`, `user_id`, `tenant_id`, `timestamp` |
| Subscription / rate-limit | Rate-limiting and subscription gates confirmed not bypassed by new report path |

### G2 — Migration Safety Green

| Check | Requirement |
|---|---|
| Schema reviewed | `011_posted_journal_entries_schema.sql` reviewed by engineering owner |
| Additive-only confirmed | No DROP, ALTER DROP COLUMN, UPDATE, DELETE in migration file |
| Dry-run passed | Migration executed in disposable/staging DB; no errors; rollback plan tested |
| Rollback plan | `DROP TABLE` sequence documented and tested in disposable DB |

### G3 — Fixture Pack Green

| Check | Requirement |
|---|---|
| Fixture valid | `synthetic_posted_ledger_fixture_pack.json` passes all H25/H26 contract tests |
| No PII | No real personal IDs, tax numbers, IBANs, email addresses |
| All 11 reports covered | `expected_reports.tenant_alpha` has all 11 report types |
| Totals deterministic | H26 expected totals match line-by-line Decimal calculation |

### G4 — Fixture Load Green

| Check | Requirement |
|---|---|
| Disposable/staging DB only | Fixture loaded into `bridgehub_disposable_*` or `bridgehub_test_*` on localhost |
| No production data | Zero real customer rows |
| Balancing checks pass | All posted/correction headers: total_debit = total_credit |
| Tenant isolation pass | tenant_alpha rows absent from tenant_beta outputs and vice versa |

### G5 — Old-vs-New Runtime Comparison Green

| Check | Requirement |
|---|---|
| Legacy path captured | All 11 report outputs captured with `POSTED_LEDGER_REPORTS_ENABLED=false` |
| Posted-ledger path captured | All 11 report outputs captured with `POSTED_LEDGER_REPORTS_ENABLED=true` on disposable DB only |
| Normalizer passes | H28 normalizer contract tests green on both outputs |
| Comparator passes | H29 comparator contract tests green; all mismatches classified |

### G6 — Accountant Review Green

| Check | Requirement |
|---|---|
| Review report generated | H30 accountant review report produced for all 11 reports |
| No critical/high mismatches | Zero `critical` or `high` severity mismatches |
| Rounding-only accepted | If `rounding_only` mismatches exist, accountant sign-off captured |
| Sign-off captured | H30 `sign_off` object complete with signer, timestamp, scope |

### G7 — Evidence / Drilldown Green

| Check | Requirement |
|---|---|
| `source_draft_id` preserved | Non-null on all non-reversal standard-net entries |
| `posting_log_id` preserved | Non-null on all standard-net entries (H001–H012) |
| `evidence_bundle_id` present | On high-evidence entries (payroll, VAT, correction) |
| Drilldown functional | Report row → journal entry → source draft → evidence link navigable |
| Missing evidence policy | Zero required evidence links absent in G6 comparison output |

### G8 — Monitoring Green

| Check | Requirement |
|---|---|
| `/health` monitored | Health endpoint polled; alert on `status: failed` |
| `/version` SHA verified | Live commit SHA matches expected deploy SHA |
| Error rate | 5xx rate on report endpoints < 0.1% sustained |
| Report latency | p95 < 3 s for all 11 report types |
| Feature flag state | `POSTED_LEDGER_REPORTS_ENABLED` value logged and monitored |
| Tenant leakage sentinel | Log and alert if cross-tenant row detected in any report output |
| Correlation IDs | Every request and error log contains `X-Correlation-ID` |
| Alert owner | Named on-call engineer assigned before switch |

### G9 — Rollback Green

| Check | Requirement |
|---|---|
| Disable documented | Command to set `POSTED_LEDGER_REPORTS_ENABLED=false` or remove env var documented |
| Rollback owner | Named engineer assigned; reachable during switch window |
| RTO defined | Rollback time objective ≤ 15 minutes from decision to feature flag OFF |
| Post-rollback checklist | `/version`, `/health`, protected endpoints, sample reports verified after rollback |
| No data loss | Rollback cannot cause data loss in `posted_journal_entries` table |

### G10 — Security / Privacy Green

| Check | Requirement |
|---|---|
| No PII in responses | Report outputs do not contain Georgian personal IDs or company tax numbers |
| Tenant isolation | No cross-tenant rows in any report output |
| Protected endpoints | All report endpoints return 401/403 without valid JWT |
| Balance.ge isolated | Balance.ge activation is not coupled to this feature flag switch |
| Credentials unchanged | No credential rotation required as part of this switch |
| No real PII in responses | Report outputs must not expose personal IDs, tax numbers, or IBAN values |

### G11 — Production Approval Packet Complete

| Check | Requirement |
|---|---|
| Engineering sign-off | Named engineering owner; timestamp; git SHA recorded |
| Accountant sign-off | Named accountant/financial controller; timestamp; scope recorded |
| Product/business sign-off | Named product owner or business sponsor; timestamp |
| Rollback owner sign-off | Named rollback engineer; availability window confirmed |
| Packet recorded | Approval packet stored in audit system or version-controlled document |

### G12 — Post-Switch Verification Plan Ready

| Check | Requirement |
|---|---|
| Expected SHA | Local main SHA equals live `/version` SHA after deploy |
| `/health` expected | `status: ok` or `status: degraded` with known and acceptable warnings only |
| Sample reports | At least 3 of 11 report types sampled post-switch for tenant_alpha |
| Protected endpoints | `approval/queue`, `reports/trial-balance` return 401/403 without auth |
| Feature flag state | `/health` or log confirms `POSTED_LEDGER_REPORTS_ENABLED=true` in production |
| Accountant review post-switch | H30 review report generated again post-switch; no new critical/high mismatches |

---

## 7. No-Go Blockers

Any of the following immediately blocks production switch:

| Blocker | Category |
|---|---|
| Any `critical` mismatch in G6 review | Accounting integrity |
| Any `tenant leakage` detected | Security / data isolation |
| Any `status policy mismatch` | Accounting integrity |
| Any required `evidence_bundle_id` absent | Audit / evidence |
| Any required `posting_log_id` absent | Audit / drilldown |
| Migration not dry-run in disposable/staging DB | Safety |
| Fixture load not completed | Safety |
| No accountant sign-off | Approval |
| No rollback owner named | Safety |
| `POSTED_LEDGER_REPORTS_ENABLED` already enabled in production without packet | Process violation |
| Balance.ge activation coupled to this switch | Security / isolation |
| Raw credential/PII exposed in any report output | Security / privacy |
| Protected endpoint auth bypass detected | Security |
| Production DB touched outside approved plan | Process violation |
| Approval packet incomplete (any gate below G12) | Process |

---

## 8. Production Switch Request Packet

The following fields must all be populated before any Cloud Run env var change is made:

| Field | Type | Required | Description |
|---|---|---|---|
| `request_id` | string | yes | Unique packet identifier (e.g., `PSR-2026-001`) |
| `requested_by` | string | yes | Engineering owner name |
| `requested_at` | ISO 8601 | yes | Request timestamp |
| `git_sha` | string | yes | Expected production commit SHA |
| `deployment_sha` | string | yes | Live `/version` SHA at switch time |
| `feature_flag` | string | yes | `POSTED_LEDGER_REPORTS_ENABLED` |
| `target_environment` | string | yes | `production` |
| `gate_results` | object | yes | G1–G12 statuses: `passed`, `failed`, `blocked` |
| `accountant_review_report_id` | string | yes | H30 review report `review_id` |
| `rollback_plan_reference` | string | yes | Document reference or git path |
| `monitoring_plan_reference` | string | yes | Dashboard/alert reference |
| `sign_offs` | object | yes | Engineering, accountant, product, rollback owner |
| `no_go_blockers_checked` | boolean | yes | Must be `true` — confirms no-go list reviewed |
| `emergency_disable_command_reference` | string | yes | Runbook reference for immediate flag disable |

---

## 9. Sign-Off Requirements

| Role | Required | Sign-Off Scope | Constraint |
|---|---|---|---|
| Engineering owner | yes | Gate results G1–G12; git SHA; deployment plan | Cannot waive critical/high mismatches |
| Accountant / financial controller | yes | G6 review report; rounding acceptance if applicable | Must review all 11 report comparisons |
| Product / business owner | yes | Business impact acceptance; rollout scope | Cannot approve without engineering sign-off |
| Rollback owner | yes | Rollback plan; availability window; RTO | Must be reachable during switch window |
| Security / privacy reviewer | conditional | Required if any PII risk or credential change involved | Triggered by G10 findings |

Rules:
- Critical and high mismatches cannot be waived for production switch by any signer.
- Rounding-only mismatches may be accepted with accountant sign-off only.
- Each sign-off must include: signer name or ID, timestamp, scope statement.
- All sign-offs must be audit-logged in a future implementation.

---

## 10. Rollback Plan Requirements

The rollback plan must address the following before switch is approved:

| Requirement | Specification |
|---|---|
| Disable command | Documented command to set `POSTED_LEDGER_REPORTS_ENABLED` to `false` or remove env var |
| Redeploy needed? | Prefer no-redeploy if env var can be changed via Cloud Run update without code change |
| Verify after rollback | `/version`, `/health`, 3 sample report endpoints, protected endpoint 401/403 |
| No silent fallback corruption | Confirm legacy path returns correct outputs after rollback |
| Notify | Accountant owner and business owner notified within 15 minutes of rollback decision |
| Rollback audit entry | Incident reference, timestamp, who initiated, reason, outcome |
| Data safety | Rollback cannot cause data loss; `posted_journal_entries` table is read-only in report path |

---

## 11. Monitoring Plan Requirements

| Signal | Threshold | Action |
|---|---|---|
| `/health` status | `failed` → immediate alert | Page on-call; consider rollback |
| `/version` SHA | Mismatch with expected → alert | Investigate deploy state |
| Report endpoint 5xx | > 0.1% sustained 5 minutes | Page on-call |
| Report latency p95 | > 3 s sustained 5 minutes | Investigate; consider rollback |
| Tenant leakage sentinel | Any detection → immediate alert | Rollback immediately |
| Feature flag state log | Flag changed without packet → alert | Investigate; treat as incident |
| Correlation ID | Absent from any error log | Investigation required |
| On-call owner | Named engineer | Available during switch window |
| Rollback alert threshold | Any blocker signal | Rollback within RTO ≤ 15 minutes |

---

## 12. Staged Rollout Rules

No production enablement goes directly to all tenants. The staged sequence is:

1. **Disposable/local only** — feature flag ON in isolated local or Docker DB; no network exposure.
2. **Staging/non-production only** — feature flag ON in staging Cloud Run service; no production traffic.
3. **Sandbox tenant only** — feature flag ON for a single synthetic/internal tenant in staging.
4. **Internal tenant only** — feature flag ON for a Bridge Hub internal tenant; monitored closely.
5. **Limited production tenant** — feature flag ON for one approved production tenant; accountant review generated.
6. **Wider production** — feature flag ON for all tenants after limited-tenant stage verified.

Rules:
- Never enable for all tenants at the first production stage.
- Any blocker at any stage reverts to the previous stage; gate must be re-satisfied.
- Production flag remains OFF until the staged rollout has passed limited-tenant stage and all G1–G12 gates are green.

---

## 13. Emergency Disable Rules

| Item | Specification |
|---|---|
| Who can disable | Engineering owner or on-call engineer with Cloud Run write access |
| When to disable | Tenant leakage detected; 5xx > 1% sustained; accountant raises accounting discrepancy; security incident |
| Evidence trigger | Any of: tenant leakage sentinel alert; critical mismatch in production reports; report 5xx > 1%; explicit accountant objection |
| How to disable | Set `POSTED_LEDGER_REPORTS_ENABLED=false` (or remove env var) via Cloud Run update; confirm `/health` within 5 minutes |
| Who must be notified | Engineering owner; accountant owner; product/business owner; within 15 minutes |
| Audit trail | Cloud Run update event logged; incident ticket opened; timeline documented; rollback audit entry created |

---

## 14. Post-Switch Verification Checklist

After production feature flag is enabled:

| Check | Pass Condition |
|---|---|
| Local main SHA equals live `/version` SHA | `git rev-parse HEAD` == `/version.commit_sha` |
| `/health` status | `ok` or known-acceptable `degraded` only |
| Feature flag state | Log or health confirms `POSTED_LEDGER_REPORTS_ENABLED=true` |
| Protected endpoints | `approval/queue`, `reports/trial-balance`, `trade/customers` return 401/403 without auth |
| Sample official reports | 3 of 11 report types sampled; outputs match expected snapshot |
| Accountant review generated | H30 review report generated post-switch; `overall_status: passed` or `passed_with_rounding` |
| No tenant leakage | tenant_beta values absent from tenant_alpha report outputs |
| No Balance.ge side effect | `balance: demo_mode` remains in `/health`; no unintended activation |
| Rollback path confirmed | On-call engineer confirms rollback command is ready and tested |

---

## 15. Production Switch Checklist Table

| Gate | Required Evidence | Owner | Status (template) | Blocking if Failed | Notes |
|---|---|---|---|---|---|
| G1 — Trust Foundation | Credential scan pass; RBAC test pass; audit log sample | Engineering | PENDING | yes | |
| G2 — Migration Safety | Additive-only review; dry-run log; rollback test | Engineering | PENDING | yes | |
| G3 — Fixture Pack | H25/H26 test results (47/47 pass) | Engineering | PENDING | yes | |
| G4 — Fixture Load | Disposable DB load log; tenant isolation test | Engineering | PENDING | yes | |
| G5 — Old-vs-New Comparison | Normalizer + comparator output for all 11 reports | Engineering | PENDING | yes | |
| G6 — Accountant Review | H30 review report; sign-off object | Accountant | PENDING | yes | |
| G7 — Evidence / Drilldown | Drilldown test results; evidence link audit | Engineering | PENDING | yes | |
| G8 — Monitoring | Dashboard link; alert config; on-call named | Engineering | PENDING | yes | |
| G9 — Rollback | Rollback command documented; RTO confirmed | Rollback owner | PENDING | yes | |
| G10 — Security / Privacy | Tenant isolation test; protected endpoint 401/403 | Engineering | PENDING | yes | |
| G11 — Approval Packet | Completed switch request packet with all 4 sign-offs | All owners | PENDING | yes | |
| G12 — Post-Switch Plan | Verification checklist from Section 14 ready | Engineering | PENDING | yes | |

---

## 16. Sample Go / No-Go Outcomes

| Scenario | Decision | Reason |
|---|---|---|
| All G1–G12 green; packet complete; all sign-offs captured | **GO** | All gates satisfied |
| G6 shows `high` mismatch in Trial Balance totals | **NO-GO** | High mismatch blocks production; requires resolution and G6 re-run |
| G4 fixture load reveals tenant leakage in test output | **NO-GO** | Tenant leakage is a hard blocker; must resolve isolation bug first |
| G7 finds `evidence_bundle_id` null on payroll entries | **NO-GO** | Missing required evidence is a no-go; fix drilldown and re-run G7 |
| G9 rollback owner unavailable during proposed switch window | **NO-GO** | Rollback owner must be reachable; reschedule switch |
| G6 accountant sign-off not captured | **NO-GO** | Accountant sign-off is mandatory; cannot proceed without it |
| `POSTED_LEDGER_REPORTS_ENABLED=true` found in production without packet | **IMMEDIATE NO-GO** | Process violation; disable flag immediately; open incident |

---

## 17. Safety Rules

- No DB is created or connected to in H31.
- No runtime report endpoints are called in H31.
- No feature flag is enabled in H31 (`POSTED_LEDGER_REPORTS_ENABLED` stays OFF).
- No Cloud Run env vars are modified in H31.
- Balance.ge remains `demo_mode`; `BALANCE_API_KEY` absent.
- No connector behavior is changed.
- No infrastructure is changed.
- No credentials are changed.
- No UI/static files are changed.
- No runtime business logic code is modified.
- No production data is used.

---

## 18. H31 Results

| Test group | Result |
|---|---|
| H31 targeted (29 tests) | 29/29 passed |
| H30 + H31 combined (59 tests) | 59/59 passed |
| Related report/fixture tests | all passed |
| Full unit suite | 4176+ passed / 0 failed / 2 skipped |
| Fixture corrections | none |
| App code modified | none |
| Production switch gate contract green | yes |

---

## 19. Non-Goals

H31 does **not**:

- Create a DB.
- Connect to a DB.
- Execute SQL.
- Run migrations.
- Load fixture data into any DB.
- Use production data.
- Call runtime report APIs.
- Implement runtime helpers.
- Modify any file under `app/`.
- Enable `POSTED_LEDGER_REPORTS_ENABLED`.
- Modify Cloud Run env vars.
- Start the production switch.
- Activate Balance.ge.
- Change UI/static files.
- Change infrastructure.
- Change credentials.
- Start H32.

---

## 20. Next Task

Only after PR merge, deploy, and live verification of H31:

**H32 — Rollback / Monitoring / Post-Switch Safety Contract**

or:

**H32 — Controlled Non-Production Feature Flag Simulation Plan**
