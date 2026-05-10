# Balance.ge Activation — Final Gate Checklist

## A) Purpose

This document is the final, authoritative gate checklist that must be fully
satisfied before any live Balance.ge connector activation occurs in Bridge Hub.

This document is produced as part of Task 10F-H. It consolidates and extends
the 12 gates defined in `docs/balance-ge-activation-gate.md` with the full set
of Trust Foundation prerequisites established across Tasks 10E-C through 10F-G.

This document:
- Defines all required gates before live Balance.ge activation.
- States that current status for every gate is NOT MET.
- States the absolute no-activation rule.
- States the required evidence before any live connector flag is flipped.
- States forbidden activation paths.
- States safe pre-activation work allowed now.
- States activation PR requirements for a future live activation PR.
- States rollback and emergency disable policy.
- States commercial pilot boundary.

**This task is documentation and tests only.**
**This task does NOT activate Balance.ge.**
**This task does NOT configure Balance.ge credentials.**
**This task does NOT change connector code.**
**This task does NOT run live Balance.ge calls.**
**This task does NOT touch the production database.**
**This task does NOT execute SQL.**
**This task does NOT change production infrastructure.**

---

## B) Current State

As of main HEAD `a41b3de` (Task 10F-G merged and live):

- Balance.ge connector status: **DEMO** — `BALANCE_API_KEY` is absent from production environment.
- Per-tenant credentials: stored as **plaintext** TEXT in `tenant_balance_credentials.api_key` — NOT encrypted.
- Credential vault: **NOT implemented** — future Task 11C.
- Masked reads: **contract defined** (10F-C) — runtime enforcement **NOT implemented**.
- Dry-run support: **NOT implemented** — `balance_connector.py` has no `dry_run` parameter.
- Payload preview: **NOT implemented** — no accountant-facing preview step before live posting.
- Idempotency key: **NOT verified** for Balance.ge live flow.
- Evidence bundle: **NOT implemented** — `journal_drafts.evidence_bundle` column absent.
- Subscription enforcement: **contract defined** (10F-D) — runtime enforcement **NOT implemented**.
- Redis/rate-limit: **contract defined** (10F-E) — runtime enforcement **NOT implemented**.
- Backup/PITR restore drill: **plan defined** (10F-G) — drill **NOT completed**.
- Runtime DDL cutover: **plan defined** (10F-F) — migration **NOT executed**.
- Accountant pilot sign-off: **NOT obtained**.
- Live Balance.ge API calls: **NONE** — no live ERP writes have occurred.
- Production infrastructure: **unchanged** in this task.

**All gates are currently NOT MET unless explicitly proven by evidence.**

---

## C) Absolute No-Activation Rule

Balance.ge MUST NOT be activated until **ALL** of the following are true simultaneously:

1. A PR is explicitly titled as live Balance.ge activation.
2. Production credentials are stored via the implemented credential vault (Task 11C), not plaintext.
3. Masked reads are implemented and verified — no raw api_key surfaces in any response.
4. Human approval flow is verified end-to-end for the pilot tenant.
5. `dry_run=True` execution is verified and logged in `posting_logs`.
6. Payload preview is verified — accountant has reviewed and explicitly accepted the payload.
7. Idempotency is verified — duplicate posting returns existing result, not new ERP entry.
8. Posting logs are verified — all required fields present, no secrets in logs.
9. Rollback/manual fallback procedure is documented and tested.
10. Accountant pilot sign-off document exists.
11. Live verification checklist is complete for the test tenant before any production tenant.
12. All 14 gates below are MET with evidence attached to the activation PR.

**No partial activation is permitted.**
**No single-gate bypass is permitted.**
**No docs-only or test-only PR constitutes activation.**

---

## D) Final Activation Gate List

### GATE-01 — Credential Vault Implemented

**Condition:** Credential vault (Task 11C) is merged, tested, and live-verified.

Requirements:
- Encrypted-at-rest credential storage using AES-256-GCM or equivalent.
- `tenant_balance_credentials.encrypted_value` column exists and is populated.
- `tenant_balance_credentials.api_key` plaintext column is nulled out or removed.
- Service layer reads only from `encrypted_value` and never returns raw key to any API.
- Rotation metadata (`rotated_at`, `key_version`) is stored.
- Audit metadata (`last_accessed_at`, `accessed_by`) is stored.
- No raw secret exposure in any response, log, or export.
- Unit tests confirm no API-facing function returns raw `api_key`.

**Status: NOT MET**
**Reason:** Credential vault implementation has not started. `api_key` is stored as plaintext TEXT.
**Required evidence:** Vault implementation PR merged + live-verified. Unit tests for masked-only responses.
**Owner/Future task:** Task 11C-A
**Blocking severity:** CRITICAL — hard blocker for any live credential storage

---

### GATE-02 — Balance.ge Credentials Safely Stored

**Condition:** No plaintext Balance.ge credentials exist in any non-vault location.

Requirements:
- No `.env` file with a live Balance.ge `api_key`.
- No Cloud Run plaintext env var `BALANCE_API_KEY` with a real production key.
- No PR body, commit message, docs, or test fixture containing a real api_key.
- No logs containing a real api_key.
- Credentials scoped per tenant/company (not shared global key).
- Credentials referenced only through the vault interface.

**Status: NOT MET**
**Reason:** `tenant_balance_credentials.api_key` is plaintext. Credential vault not implemented.
**Required evidence:** Vault implementation + DB migration nulling plaintext column. GCP Secret Manager or vault proof.
**Owner/Future task:** Task 11C-A + 11C-B
**Blocking severity:** CRITICAL — live credential without vault is a security violation

---

### GATE-03 — Masked Read Behavior Implemented

**Condition:** All API-facing endpoints return only masked values or boolean status for credentials.

Requirements:
- Connector status endpoints return `configured`, `mode`, `last_test_status`, `last_tested_at` only.
- Masked hint (`****xxxx` format) is the maximum credential detail returned.
- No `api_key`, `password`, `token`, or `secret` value is returned in any response.
- No credential value is returned in error messages or stack traces.
- Audit events log credential access without storing the secret value.
- Runtime enforcement is active, not just a documented contract.

**Status: NOT MET**
**Reason:** Masked read behavior is defined in contract (10F-C) but runtime enforcement is not implemented.
**Required evidence:** Integration test showing status endpoint returns no raw credentials. Code diff showing enforcement.
**Owner/Future task:** Task 11C-C
**Blocking severity:** CRITICAL — raw api_key currently returned by balance_credentials_service

---

### GATE-04 — Subscription / Trial Enforcement Implemented

**Condition:** Expired or suspended tenants are blocked from connector execution.

Requirements:
- `trial_ends_at` expiry check is enforced before any connector call.
- Tenants with `status = suspended` or `status = inactive` are blocked.
- Connector execution returns an explicit `SUBSCRIPTION_REQUIRED` error for blocked tenants.
- Enforcement is runtime-active (not just documented contract).
- Autopilot does not run Balance.ge for expired/suspended tenants.

**Status: NOT MET**
**Reason:** Subscription enforcement is defined in contract (10F-D) but runtime enforcement is not implemented.
**Required evidence:** Integration test showing blocked tenant cannot trigger connector. Code diff showing enforcement middleware.
**Owner/Future task:** Task 11C-D
**Blocking severity:** HIGH — expired tenants could trigger live ERP writes

---

### GATE-05 — Redis / Rate-Limit Protection Implemented

**Condition:** Auth, credential, and connector endpoints are throttled by Redis-backed rate limiting.

Requirements:
- Connector test/execution endpoints are throttled (e.g., max 10/min per tenant).
- Credential setup/update endpoints are throttled (e.g., max 5/min per user).
- Auth endpoints are throttled (e.g., max 10/min per IP).
- Rate limit fallback is not unlimited (in-memory fallback with a conservative cap).
- Redis-backed enforcement is active in production, not just documented contract.

**Status: NOT MET**
**Reason:** Rate-limit architecture is defined (10F-E) but runtime Redis enforcement is not implemented.
**Required evidence:** Load test showing connector endpoint throttled. Redis key inspection. Code diff.
**Owner/Future task:** Task 11C-E
**Blocking severity:** HIGH — unlimited connector calls could produce runaway ERP writes

---

### GATE-06 — Approval-First Workflow Verified

**Condition:** No live Balance.ge posting can occur without a human-approved journal draft.

Requirements:
- Journal draft must reach `approved` status before posting is triggered.
- Posting without an approved draft returns an error (`DRAFT_NOT_APPROVED` or similar).
- Unauthorized approval attempts are rejected by RBAC.
- Audit event is recorded for every approval action.
- Autopilot approvals also produce a proper audit trail.
- CFO dual-approval threshold is enforced for large amounts.

**Status: NOT MET**
**Reason:** Approval-first workflow exists in code but end-to-end verification with a live Balance.ge connector is not complete.
**Required evidence:** End-to-end test: document → draft → human approval → posting trigger. Posting-without-approval error proof.
**Owner/Future task:** Task 11C-F (live verification step)
**Blocking severity:** CRITICAL — the entire safety model depends on approval-first enforcement

---

### GATE-07 — Dry-Run and Payload Preview Verified

**Condition:** Balance.ge connector supports verified dry-run mode and accountant-facing payload preview.

Requirements:
- `balance_connector.py` supports `dry_run=True` parameter.
- Dry-run execution reaches Balance.ge sandbox (or is logged as dry_run without a live call if no sandbox).
- `posting_logs` entry created with `mode = dry_run`.
- Payload preview shows accountant: journal lines, account codes, amounts, VAT, counterparty, date, reference, idempotency key.
- Accountant must explicitly accept the previewed payload before live execution.
- Actual sent payload matches previewed payload hash.
- No live ERP write occurs before dry-run and payload preview are both verified.

**Status: NOT MET**
**Reason:** `balance_connector.py` has no `dry_run` parameter. No payload preview step exists.
**Required evidence:** Dry-run code diff. Dry-run `posting_logs` sample. UI/API payload preview screenshot or test output.
**Owner/Future task:** Task 11C-G (connector dry-run implementation)
**Blocking severity:** CRITICAL — no dry-run means first execution is a live ERP write

---

### GATE-08 — Posting Idempotency Verified

**Condition:** Duplicate posting attempts are safely rejected without creating a second ERP entry.

Requirements:
- Every posting attempt uses a unique `idempotency_key` derived from `draft_id` + `tenant_id` + `connector`.
- `posting_logs` stores `idempotency_key` and `entry_hash` for every attempt.
- Sending the same approved draft twice returns the existing posting log result.
- Connector retry on transient failure does not create a duplicate ERP entry.
- Verified specifically for Balance.ge live flow (not only for unit tests).

**Status: NOT MET**
**Reason:** `entry_hash` exists in code but idempotency is not verified for Balance.ge live flow. No `idempotency_key` in `balance_connector.py`.
**Required evidence:** Integration test: duplicate posting returns existing result. `posting_logs` sample showing idempotency_key.
**Owner/Future task:** Task 11C-G
**Blocking severity:** HIGH — duplicate ERP entries are an accounting integrity violation

---

### GATE-09 — Posting Logs and Audit Trail Verified

**Condition:** Every Balance.ge execution attempt is logged with all required fields and without secrets.

Required `posting_logs` fields per entry:
- `tenant_id`
- `draft_id`
- `connector` (value: `balance`)
- `idempotency_key`
- `request_payload_summary` (no credentials, no raw api_key)
- `response_payload_summary`
- `status` (`pending` / `success` / `failed` / `dry_run`)
- `error_code` (if failed)
- `error_message` (no secrets)
- `actor` (who triggered the posting)
- `created_at`
- `mode` (`live` / `dry_run` / `demo`)

**Status: NOT MET**
**Reason:** Posting logs exist but required fields for Balance.ge are not fully verified. No secrets-in-logs audit performed.
**Required evidence:** Posting log sample from dry-run execution showing all fields. No-secrets scan of log output.
**Owner/Future task:** Task 11C-G
**Blocking severity:** HIGH — incomplete logs prevent audit and recovery

---

### GATE-10 — Evidence Bundle Ready

**Condition:** Every approved action carries a populated evidence bundle before reaching the connector.

Requirements:
- `journal_drafts.evidence_bundle` JSONB column exists and is populated.
- Source document or bank transaction reference (hash, object ID, or GCS path) is stored.
- AI reasoning and classification explanation are stored.
- Approval event (approver, timestamp, payload hash) is stored.
- Connector payload preview and hash are stored before execution.
- Posting result (connector response, ERP ID) is appended after execution.
- Evidence is reproducible and auditable independently of the journal draft state.

**Status: NOT MET**
**Reason:** `evidence_bundle` column is absent. No evidence attachment occurs anywhere in the current flow.
**Required evidence:** DB migration adding column. Code showing evidence population at each step. Sample evidence bundle JSON.
**Owner/Future task:** Task 11C-E
**Blocking severity:** HIGH — without evidence bundles the audit trail is incomplete

---

### GATE-11 — Backup / PITR and Restore Drill Ready

**Condition:** Automated backups are verified, PITR is enabled, and a restore drill is complete.

Requirements:
- Cloud SQL automated backups are enabled and verified.
- PITR (point-in-time recovery) is enabled for the production Cloud SQL instance.
- At least one restore drill has been completed without overwriting production.
- Restore drill result is documented in the evidence bundle.
- Static files backup from GCS is verified (10F-G plan).
- Backup schedule and retention policy are documented.

**Status: NOT MET**
**Reason:** Backup/PITR plan is defined (10F-G) but restore drill has not been completed.
**Required evidence:** Cloud SQL backup console screenshot. PITR enabled confirmation. Restore drill report.
**Owner/Future task:** Task 11C-H (ops verification)
**Blocking severity:** MEDIUM — live activation without backup/PITR verified is an operational risk

---

### GATE-12 — Rollback / Manual Fallback Ready

**Condition:** A tested rollback path and manual fallback procedure exist for connector failures.

Requirements:
- Balance.ge connector can be disabled per-tenant without code change (config flag or credential removal).
- Accountant can export approved journal lines as CSV or structured doc for manual Balance.ge entry.
- Failed posting keeps `journal_drafts.status = approved` (not moved to `posted`) until confirmed.
- Idempotency key prevents duplicate after retry.
- `posting_logs` record for failed attempt is accessible and shows what was attempted.
- Support runbook exists and is linked from this document.
- Accountant knows the rollback procedure before live activation.

**Status: NOT MET**
**Reason:** No per-tenant connector disable flag. No manual export fallback. No support runbook.
**Required evidence:** Disable flag implementation. Manual export endpoint or script. Runbook document.
**Owner/Future task:** Task 11C-G + pilot runbook
**Blocking severity:** HIGH — no rollback path means a bad posting has no recovery

---

### GATE-13 — Accountant Pilot Sign-Off

**Condition:** A qualified Georgian accountant has reviewed and signed off on the pilot scope.

Requirements:
- Pilot tenant is selected and isolated from other production tenants.
- Accountant has reviewed: COA mapping, VAT treatment for pilot document types, connector payload format.
- Accountant has confirmed the proposed posting output matches Balance.ge expectations.
- RS.ge implications (VAT registers) are reviewed.
- Written sign-off document or approval record exists.
- Acceptance criteria for the pilot are documented and approved.

**Status: NOT MET**
**Reason:** No accountant review has occurred. No pilot tenant is selected.
**Required evidence:** Written accountant sign-off. COA mapping review document. Pilot tenant designation.
**Owner/Future task:** Commercial pilot preparation (post Task 11C)
**Blocking severity:** CRITICAL — live accounting without accountant review is an accounting integrity risk

---

### GATE-14 — Live Verification Checklist Complete

**Condition:** Full live verification is completed on the test tenant before any production tenant activation.

Requirements:
1. Live `/version` endpoint matches expected commit SHA.
2. `/health` returns 200 and is stable.
3. Static pages load correctly.
4. Protected endpoints reject unauthenticated requests.
5. Balance.ge status endpoint returns `configured`/`not_configured` only — no raw credentials.
6. No raw credentials visible in any response, log, or browser console.
7. Dry-run posting on test tenant completes and log entry is verified.
8. Duplicate dry-run posting returns existing result (idempotency verified).
9. Subscription enforcement blocks an expired/suspended test tenant.
10. Rate limit triggers on excessive connector calls.
11. Accountant confirms payload preview is readable and correct.
12. Rollback test: connector disabled, accountant receives clear error.

**Status: NOT MET**
**Reason:** Live verification cannot be completed until all preceding gates are MET.
**Required evidence:** Live verification report document with screenshots/logs for each step.
**Owner/Future task:** Final step before production tenant activation
**Blocking severity:** CRITICAL — must be the last gate verified before any production activation

---

## E) Current Gate Status Table

| Gate | Name | Status | Reason | Blocking Severity |
|---|---|---|---|---|
| GATE-01 | Credential Vault Implemented | NOT MET | Vault not implemented; plaintext api_key in DB | CRITICAL |
| GATE-02 | Balance.ge Credentials Safely Stored | NOT MET | api_key stored as plaintext TEXT | CRITICAL |
| GATE-03 | Masked Read Behavior Implemented | NOT MET | Contract defined; runtime enforcement absent | CRITICAL |
| GATE-04 | Subscription/Trial Enforcement Implemented | NOT MET | Contract defined; runtime enforcement absent | HIGH |
| GATE-05 | Redis/Rate-Limit Protection Implemented | NOT MET | Contract defined; runtime Redis enforcement absent | HIGH |
| GATE-06 | Approval-First Workflow Verified | NOT MET | Code exists; end-to-end live verification absent | CRITICAL |
| GATE-07 | Dry-Run and Payload Preview Verified | NOT MET | dry_run param absent from balance_connector.py | CRITICAL |
| GATE-08 | Posting Idempotency Verified | NOT MET | Partial code; not verified for live Balance.ge flow | HIGH |
| GATE-09 | Posting Logs and Audit Trail Verified | NOT MET | Required fields not fully verified; secrets scan absent | HIGH |
| GATE-10 | Evidence Bundle Ready | NOT MET | evidence_bundle column absent; no population code | HIGH |
| GATE-11 | Backup/PITR and Restore Drill Ready | NOT MET | Plan defined; restore drill not completed | MEDIUM |
| GATE-12 | Rollback / Manual Fallback Ready | NOT MET | No disable flag; no manual export; no runbook | HIGH |
| GATE-13 | Accountant Pilot Sign-Off | NOT MET | No accountant review; no pilot tenant selected | CRITICAL |
| GATE-14 | Live Verification Checklist Complete | NOT MET | Cannot complete until all other gates are MET | CRITICAL |

**Current activation status: BLOCKED — 0 of 14 gates are MET.**

---

## F) Evidence Required Before Activation

The activation PR must include all of the following as attachments or linked
documents before any reviewer approves it:

| Evidence Item | Required For Gate | Format |
|---|---|---|
| `credential_vault_proof` | GATE-01, GATE-02 | Code diff + unit test output showing no raw key in responses |
| `masked_status_response_no_secrets` | GATE-03 | Test output or screenshot showing status endpoint returns no raw credentials |
| `dry_run_output` | GATE-07 | `posting_logs` record with `mode = dry_run` |
| `payload_preview_output` | GATE-07 | Accountant-facing preview JSON with all required fields |
| `approved_draft_id` | GATE-06 | Draft ID used in the live verification dry-run |
| `idempotency_duplicate_test` | GATE-08 | Test log showing duplicate posting returns existing result |
| `posting_log_sanitized_sample` | GATE-09 | `posting_logs` row with all required fields and no secrets |
| `rollback_proof` | GATE-12 | Connector disabled → accountant receives clear error |
| `accountant_signoff` | GATE-13 | Written sign-off document |
| `backup_pitr_evidence` | GATE-11 | Cloud SQL backup/PITR console screenshot + restore drill report |
| `rate_limit_evidence` | GATE-05 | Log showing connector endpoint throttled at configured limit |
| `subscription_enforcement_evidence` | GATE-04 | Test showing expired tenant blocked from connector execution |
| `live_verification_report` | GATE-14 | All 12 live verification steps documented with outcomes |

---

## G) Forbidden Activation Paths

Balance.ge MUST NOT be activated via any of the following paths:

| Forbidden Path | Why |
|---|---|
| `plaintext_env_only` | Adding `BALANCE_API_KEY` as a plaintext Cloud Run env var bypasses the credential vault requirement |
| `bypass_credential_vault` | Any activation that does not use the implemented vault violates GATE-01 and GATE-02 |
| `direct_connector_call_without_approval` | Any connector call that skips the approval flow violates GATE-06 |
| `direct_db_update` | Setting credentials via raw SQL or DB console bypasses vault and audit trail |
| `manual_sql` | SQL executed directly against production DB bypasses all safety controls |
| `hidden_feature_flag` | A flag that activates Balance.ge without a PR review is not permitted |
| `unreviewed_workflow_secret_change` | Adding `BALANCE_API_KEY` to a GitHub Actions secret without PR review bypasses security review |
| `docs_only_pr` | A docs-only PR does not constitute activation evidence |
| `test_only_pr` | A test-only PR does not constitute activation evidence |
| `local_only_proof` | Evidence that exists only on a developer's local machine is not accepted |

---

## H) Safe Pre-Activation Work Allowed

The following work is safe to perform without triggering Balance.ge activation:

| Safe Work | Description |
|---|---|
| `docs_tests` | Documentation and test-only work (this task) |
| `connector_interface_tests` | Tests that verify the connector interface contract without calling the live API |
| `fake_connector_tests` | Tests using a fake/stub connector that never sends real HTTP requests |
| `dry_run_only_tests` | Tests that verify dry_run=True mode using mocked Balance.ge responses |
| `payload_preview_tests` | Tests that verify the payload preview format without live execution |
| `credential_vault_implementation` | Implementing the vault (Task 11C) does not activate Balance.ge |
| `masked_reads_implementation` | Implementing masked read enforcement does not activate Balance.ge |
| `subscription_rate_limit_implementation` | Implementing enforcement middleware does not activate Balance.ge |
| `evidence_bundle_implementation` | Adding evidence_bundle column and population code does not activate Balance.ge |
| `no_live_posting` | Any work that does not result in an HTTP POST to `https://api.balance.ge` is safe |

---

## I) Activation PR Requirements

A future Balance.ge activation PR MUST satisfy all of the following:

| Requirement | Description |
|---|---|
| `explicit_live_activation_title` | PR title must explicitly state: "live Balance.ge activation" or equivalent |
| `all_gates_evidence` | All 14 gates must be listed with status MET and evidence attached |
| `rollback_plan` | Rollback procedure must be documented and linked |
| `manual_fallback_plan` | Manual accountant fallback (CSV export + manual Balance.ge entry) must be documented |
| `accountant_signoff` | Written accountant sign-off must be attached |
| `live_verification_steps` | All 12 GATE-14 live verification steps must be documented with outcomes |
| `no_secrets_proof` | PR body/diff must contain no raw credentials; secrets scan must pass |
| `approved_tenant_pilot_scope` | The PR must explicitly name the pilot tenant(s) being activated |
| `limited_activation_scope` | Activation must be scoped to the named pilot tenant only — no broad rollout |
| `final_human_approval` | At least one qualified human reviewer must approve the PR before merge |

---

## J) Rollback / Emergency Disable Policy

If a live Balance.ge posting must be halted immediately:

1. **Emergency disable flag**: Remove or blank the Balance.ge `api_key` from the credential vault for the affected tenant. This puts the connector back to `demo` mode within seconds.
2. **Connector disabled state**: Connector returns a safe demo response when `api_key` is absent. No live ERP writes occur.
3. **Revoke credentials**: Revoke the Balance.ge API key via the Balance.ge console immediately.
4. **Stop posting**: Disable autopilot for the affected tenant (remove from `tenants` table `status` or set to `suspended`).
5. **Keep read/status safe**: Status and health endpoints continue to work after disable. No crash.
6. **Preserve posting logs**: Do not delete `posting_logs` records. These are the audit trail and recovery guide.
7. **Notify pilot accountant/admin**: Send immediate notification to the accountant and Bridge Hub admin.
8. **Post-incident report**: Within 48 hours, document: what was posted, what the error was, what was reverted, and how future recurrence is prevented.

---

## K) Commercial Pilot Boundary

Before any commercial pilot with live Balance.ge posting:

- All 14 gates must be MET.
- Balance.ge activation must be tenant-scoped — activated for one named pilot tenant only.
- No broad rollout across all tenants.
- No auto-posting without explicit human approval per draft.
- No autonomous live posting (autopilot must have a human-in-the-loop review step for pilot phase).
- Support contact and manual fallback must be documented and reachable.
- Pilot scope must be agreed with the pilot tenant's accountant before activation.
- Pilot duration and success criteria must be defined before activation.

---

## L) Explicit Non-Goals of This Task (10F-H)

The following are explicitly NOT done in this task:

- No live Balance.ge activation.
- No Balance.ge credential changes.
- No connector code changes (`balance_connector.py` is unchanged).
- No production database changes.
- No SQL execution.
- No infrastructure changes (Cloud Run, Cloud SQL, GCP Secret Manager).
- No GitHub Actions workflow changes.
- No Task 11C implementation started.
- No migrations created.
- No runtime `app/startup/*` or `app/api/*` code changed.

---

## M) Test Strategy

Tests in `tests/unit/test_balance_ge_activation_final_checklist.py` are read-only:

- Check all required docs exist.
- Check all 14 gates are listed in the gate set with NOT MET status.
- Check no gate is MET in this task.
- Check activation_allowed logic returns False when any gate is NOT MET.
- Check required evidence set is complete.
- Check forbidden activation paths set is complete.
- Check safe pre-activation work set is complete.
- Check activation PR requirements are complete.
- Read `app/api/connectors/balance_connector.py` and `app/api/services/balance_credentials_service.py` as text to confirm Balance.ge references exist and no dry_run param is present.
- Assert no runtime/connector/network imports in the test file itself.
- Assert Balance.ge remains inactive (no `BALANCE_API_KEY` in environment).

---

## N) Future Implementation Sequence

Implementation should proceed in this order after all 10F tasks are merged and verified:

| Task | Scope | Gate |
|---|---|---|
| 11C-A | Credential vault encryption implementation | GATE-01, GATE-02 |
| 11C-B | Credential vault DB migration | GATE-01, GATE-02 |
| 11C-C | Masked read runtime enforcement | GATE-03 |
| 11C-D | Subscription/trial enforcement middleware | GATE-04 |
| 11C-E | Redis/rate-limit runtime implementation | GATE-05, evidence bundle |
| 11C-F | Evidence bundle DB column + population | GATE-10 |
| 11C-G | Balance.ge dry-run + idempotency + posting logs | GATE-07, GATE-08, GATE-09 |
| 11C-H | Backup/PITR restore drill | GATE-11 |
| 11C-I | Rollback/manual fallback + runbook | GATE-12 |
| Pilot prep | Accountant review + sign-off | GATE-13 |
| Pilot gate | Live verification on test tenant | GATE-14 |
| Activation PR | Explicit named live Balance.ge activation PR | All 14 gates MET |

**No activation PR should be raised until all 11C tasks are complete and verified.**

Cross-references:
- `docs/balance-ge-activation-gate.md` — original 12-gate checklist (superseded by this document for final authority)
- `docs/trust-foundation-implementation-plan.md` — Trust Foundation roadmap
- `docs/credential-vault-design.md` — credential vault design
- `docs/masked-read-behavior-contract.md` — masked read behavior contract
- `docs/subscription-enforcement-plan.md` — subscription/trial enforcement plan
- `docs/redis-rate-limit-plan.md` — Redis/rate-limit plan
- `docs/backup-pitr-static-files-plan.md` — backup/PITR plan
- `docs/runtime-ddl-cutover-plan.md` — DDL cutover plan
