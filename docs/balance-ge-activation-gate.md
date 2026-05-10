# Balance.ge Activation Gate

## Purpose

This document defines the conditions that must be verified before Bridge Hub can
activate Balance.ge live posting for any tenant.

Balance.ge must remain in demo or dry-run mode until **all** gate criteria below
are verified, tested, and documented. No partial activation is permitted.

This document is part of Task 10E-F Trust Foundation Implementation Plan.

---

## Current State

Balance.ge connector status as of main HEAD ac8d777:

- Mode: **DEMO** (BALANCE_API_KEY is absent from production environment)
- Per-tenant credentials: stored as **plaintext** TEXT in `tenant_balance_credentials.api_key`
- Dry-run support: **not implemented**
- Payload preview: **not implemented**
- Evidence bundle: **not implemented**
- Activation gate: **not verified**

No live ERP writes have occurred. Balance.ge activation is explicitly deferred.

---

## Gate Criteria

### Gate 1 — Encrypted Credentials Complete

**Condition:** Credential encryption implementation (Task 11C-A) is merged, tested,
and live-verified.

Required evidence:
- `tenant_balance_credentials.encrypted_value` column exists and is populated.
- `tenant_balance_credentials.api_key` plaintext column is nulled out or removed.
- Service layer (`balance_credentials_service.py`) reads from `encrypted_value`
  only and never returns the raw key to any API response.
- Unit tests confirm no API-facing function returns the raw api_key.

**Status:** NOT MET

---

### Gate 2 — Masked Reads Complete

**Condition:** All API-facing endpoints for Balance.ge credential status return
only masked values or boolean status. The raw api_key is never surfaced in any
response, log, export, or frontend state after initial setup.

Required evidence:
- Connector status endpoint returns `configured`, `mode`, `last_test_status`,
  `last_tested_at`, and optionally `masked_key` (`****xxxx` format).
- No API, log, or export contains the raw Balance.ge API key after setup.
- Audit events for credential access, update, and test are present without
  storing the key value.

**Status:** NOT MET

---

### Gate 3 — Approval-First Flow Verified End-to-End

**Condition:** The full approval-first workflow is verified for the pilot tenant:
document/draft creation → AI classification → human preview → approve → posting
trigger. No step in the workflow allows posting without an approved draft.

Required evidence:
- End-to-end test or manual verification: a document goes through OCR, produces
  a journal draft, is previewed, approved by a human approver, and reaches the
  posting trigger step.
- Autopilot approval (if used) also produces a proper audit trail.
- Posting without an approved draft returns an error.

**Status:** NOT MET (approval-first workflow exists in code but end-to-end
verification with Balance.ge is not complete)

---

### Gate 4 — Evidence Bundle Implemented and Attached

**Condition:** The evidence bundle schema (Task 11C-E) is implemented and every
approved action carries a populated evidence bundle before it reaches the
connector.

Required evidence:
- `journal_drafts.evidence_bundle` JSONB column exists.
- OCR or bank parser populates source document reference and extracted fields.
- Approval event is recorded in the bundle.
- Connector payload preview is stored in the bundle before execution.
- Posting result is appended to the bundle after execution.

**Status:** NOT MET

---

### Gate 5 — Idempotency Verified

**Condition:** Duplicate posting attempts are rejected and return the existing
result rather than creating a new ERP entry.

Required evidence:
- `posting_logs` contains `entry_hash` or `idempotency_key` for every posting
  attempt.
- Sending the same approved draft twice returns the existing posting log result,
  not a second ERP entry.
- Connector retry on transient failure does not create a duplicate entry.

**Status:** Partially implemented (entry_hash exists in code) but not verified
for Balance.ge live flow.

---

### Gate 6 — Dry-Run Mode Verified

**Condition:** Balance.ge connector supports and exercises a dry-run mode that
sends the payload to Balance.ge's sandbox or dry-run endpoint without writing
to the production ERP.

Required evidence:
- Balance.ge API supports a dry-run or sandbox mode (verify with Balance.ge docs).
- `balance_connector.py` `dry_run=True` parameter exists and is tested.
- A dry-run execution for the pilot tenant completes without creating a
  production ERP entry.
- The dry-run result is logged in `posting_logs` with `mode: dry_run`.

**Status:** NOT MET

---

### Gate 7 — Payload Preview Verified

**Condition:** Before any live execution, the exact JSON or data payload that
will be sent to Balance.ge is shown to the accountant in the approval UI and
must be explicitly accepted as part of the approval decision.

Required evidence:
- Approval UI shows the connector payload in a readable format.
- The payload includes: journal lines, account codes, amounts, VAT details,
  counterparty, date, reference, and idempotency key.
- The accountant must click an explicit "Approve for Balance.ge execution"
  button that records the payload hash in the approval event.
- The actual sent payload matches the previewed payload hash.

**Status:** NOT MET

---

### Gate 8 — Posting Logs Verified

**Condition:** Every Balance.ge execution attempt, success, and failure is logged
in `posting_logs` with all required fields and without any secret values.

Required fields per posting log entry:
- `tenant_id`
- `draft_id`
- `connector` (value: `balance`)
- `idempotency_key`
- `request_payload_summary` (no credentials, no raw API keys)
- `response_payload_summary`
- `status` (pending / success / failed / dry_run)
- `error_code` (if failed)
- `error_message` (no secrets)
- `actor` (who triggered the posting)
- `created_at`
- `mode` (live / dry_run / demo)

Required evidence:
- A test posting (dry-run) produces a `posting_logs` entry with all required fields.
- No secret value appears in any posting log field.

**Status:** Posting logs exist but required fields for Balance.ge are not fully
verified.

---

### Gate 9 — Test Tenant Verified

**Condition:** At least one full end-to-end dry-run cycle is completed on an
isolated test tenant (not a real paying tenant, not production data) before any
production tenant is activated.

Required evidence:
- A dedicated test tenant exists in the system.
- The test tenant has a Balance.ge test/sandbox API key (not a production key).
- The full flow is exercised: document → draft → approval → dry-run posting → log.
- The test tenant's data is isolated from all other tenants.
- A qualified accountant or senior engineer has reviewed the posting output and
  confirmed it is correct.

**Status:** NOT MET

---

### Gate 10 — Accountant Review Complete

**Condition:** A qualified Georgian accountant has reviewed:
- The proposed journal lines and account codes (COA mapping).
- The VAT treatment for the pilot document types.
- The connector payload format and field mapping.
- The RS.ge implications (if the posting affects VAT registers).
- The proposed posting output matches what the accountant would expect to see in
  Balance.ge.

Required evidence:
- Written accountant sign-off document or approval record.
- COA mapping review completed.
- VAT treatment confirmed for the pilot document category.

**Status:** NOT MET

---

### Gate 11 — Rollback / Manual Fallback Documented

**Condition:** If Balance.ge returns an error or the connector fails mid-execution,
the system has a defined manual fallback path and the accountant knows how to use it.

Required evidence:
- Documentation explaining: if the connector fails, the accountant can export
  the approved journal lines as a CSV or structured document and post manually
  to Balance.ge.
- The `posting_logs` record for the failed attempt is accessible and shows what
  was attempted.
- The journal draft remains in `approved` status (not moved to `posted`) until
  a successful posting confirmation is received.
- Rollback policy: if a posting is accidentally sent twice, the idempotency key
  prevents a duplicate. If Balance.ge creates a duplicate despite idempotency
  (unlikely), the accountant has a documented reversal procedure.

**Status:** NOT MET

---

### Gate 12 — Production Secrets Configured Safely

**Condition:** The Balance.ge API key for production tenant(s) is configured as
a Cloud Run secret reference (not a plaintext environment variable) and is
encrypted at rest in the Cloud Run secret store or GCP Secret Manager.

Required evidence:
- `BALANCE_API_KEY` is not set as a plaintext Cloud Run environment variable.
- The API key is either:
  (a) Stored in GCP Secret Manager and referenced via Cloud Run secret mounting,
  or
  (b) Stored encrypted in `tenant_balance_credentials.encrypted_value` and
      decrypted at runtime by the credential service.
- The key is not visible in Cloud Run console environment variable list as
  plaintext.

**Status:** NOT MET (currently BALANCE_API_KEY would be set as a plaintext env var)

---

## Activation Checklist Summary

| Gate | Condition | Status |
|---|---|---|
| 1 | Credential encryption complete | NOT MET |
| 2 | Masked reads complete | NOT MET |
| 3 | Approval-first flow verified end-to-end | NOT MET |
| 4 | Evidence bundle implemented and attached | NOT MET |
| 5 | Idempotency verified | Partial |
| 6 | Dry-run mode verified | NOT MET |
| 7 | Payload preview verified | NOT MET |
| 8 | Posting logs verified | Partial |
| 9 | Test tenant verified | NOT MET |
| 10 | Accountant review complete | NOT MET |
| 11 | Rollback / manual fallback documented | NOT MET |
| 12 | Production secrets configured safely | NOT MET |

**All 12 gates must be MET before any production tenant can execute a live
Balance.ge posting.**

---

## Live Verification Checklist (for use after all gates pass)

Before activating any production tenant on live Balance.ge:

1. Confirm `trial_ends_at` enforcement is live (subscription enforcement task
   must be complete).
2. Confirm rate limiting is Redis-backed in production.
3. Confirm `posting_logs` table is accessible and empty for the test tenant.
4. Perform one dry-run execution on the test tenant. Confirm dry-run log entry.
5. Have the accountant review the payload preview for a real document.
6. Perform one live execution on the test tenant with a low-value entry.
7. Confirm Balance.ge shows the entry correctly.
8. Confirm posting log has status=success and full evidence bundle reference.
9. Attempt a duplicate posting. Confirm idempotency returns existing result.
10. Confirm `/health` returns 200 after live execution.
11. Only after all 10 steps: activate the pilot production tenant.

---

## What Must Not Happen

- Do not activate Balance.ge before all 12 gate criteria are MET.
- Do not use a production tenant for the first dry-run test.
- Do not store the Balance.ge API key as a plaintext environment variable in
  production.
- Do not proceed without accountant review of the COA mapping and VAT treatment.
- Do not activate Balance.ge for any tenant whose trial_ends_at has expired.
- Do not skip the idempotency verification step.
- Do not skip the payload preview approval step.
- Do not activate without a documented rollback/manual fallback procedure.
