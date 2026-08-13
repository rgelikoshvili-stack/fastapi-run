# RS.ge — Controlled Live Pilot Plan

## Purpose

This document defines the graduated rollout plan for enabling live RS.ge actions in production. The goal is to move from test-mode-only to live production confirms/rejects/corrects in a controlled, auditable way with human checkpoints at every gate.

---

## Current State (Pre-Pilot)

```
RSGE_ENABLED=true
RSGE_TEST_MODE=true
RSGE_LIVE_ACTIONS_ENABLED=false
RSGE_ALLOW_TEST_CONFIRM=false
RSGE_ALLOW_TEST_REJECT=false
RSGE_ALLOW_TEST_CORRECT=false
RSGE_ALLOW_TEST_CANCEL=false
RSGE_ALLOW_TEST_ACTIVATE=false
```

All RS.ge mutations blocked. Read-only + sync + draft creation only.

---

## Phase 0 — Prerequisites (Must Complete Before Pilot)

- [ ] Test suite 246/246 passing
- [ ] Safety scan clean (no leaked tokens, no production flags enabled)
- [ ] `rsge_comparison_results` table deployed to production
- [ ] Own TIN configured for tenant via `/rs-ge/own-tin`
- [ ] At least 5 partner maps seeded via `/rs-ge/partner-map`
- [ ] At least 1 full waybill synced, evidenced, and drafted
- [ ] RBAC roles confirmed: accountant + admin for the pilot tenant
- [ ] Audit log table verified (`rsge_actions`)

---

## Phase 1 — Test-Confirm Single Waybill (T+0)

**Prerequisites:** Phase 0 complete.

**Action:**
1. Enable `RSGE_ALLOW_TEST_CONFIRM=true` on Cloud Run (env var)
2. Select 1 waybill in status=0 (saved/draft)
3. Run `POST /rs-ge/waybills/{id}/preview-activate`
4. Review preview output — check accounting impact + credentials redacted
5. Accountant reviews and records `approved_by` user_id
6. Run `POST /rs-ge/waybills/{id}/test-activate` with `approved_by`
7. Verify: `rsge_actions` log written, waybill status updated in local DB

**Pass criteria:**
- Audit log entry written (before + after)
- Waybill status changed from 0 → expected
- No credentials in response
- No accounting entry auto-posted

**Rollback:** Set `RSGE_ALLOW_TEST_ACTIVATE=false`

---

## Phase 2 — Test-Confirm Single Invoice (T+1d)

**Prerequisites:** Phase 1 pass.

**Action:**
1. Enable `RSGE_ALLOW_TEST_CONFIRM=true`
2. Select 1 invoice in status=0 from `/rs-ge/invoices`
3. Sync + evidence + draft + comparison (run `compare?target=evidence`)
4. Preview-confirm → accountant review
5. Test-confirm with `approved_by`
6. Verify audit + status + no auto-post

**Pass criteria:** Same as Phase 1.

---

## Phase 3 — Test-Reject + Test-Cancel (T+3d)

**Prerequisites:** Phase 2 pass.

**Action:**
1. Enable `RSGE_ALLOW_TEST_REJECT=true`, `RSGE_ALLOW_TEST_CANCEL=true`
2. Select 1 document in appropriate status
3. Preview-reject → review → test-reject
4. Preview-cancel → review → test-cancel
5. Verify audit for each action

---

## Phase 4 — Test-Correct (T+7d)

**Prerequisites:** Phase 3 pass, at least 1 confirmed document.

**Action:**
1. Enable `RSGE_ALLOW_TEST_CORRECT=true`
2. Select 1 confirmed document needing correction
3. `POST /rs-ge/documents/{id}/create-correction-draft` — review draft
4. Preview-correct → review → test-correct
5. Verify comparison result: was a mismatch fixed?

---

## Phase 5 — Batch Test-Confirm 5 Documents (T+14d)

**Prerequisites:** Phases 1-4 all pass, no errors in audit log.

**Action:**
1. Select 5 documents with diverse statuses
2. Run preview → review → test-action for each
3. Check all 5 audit entries
4. Run comparison on each after action

**Pass criteria:** 5/5 success, 0 errors.

---

## Phase 6 — Live Confirm 1 Document (T+30d, manual sign-off required)

**Prerequisites:**
- Phase 5 complete
- Legal/compliance sign-off
- CEO / CFO approval
- 2-factor RBAC confirmation

**Action:**
1. Enable `RSGE_LIVE_ACTIONS_ENABLED=true` (requires Cloud Run re-deploy)
2. Select 1 low-risk document for live confirm
3. Preview → review → live-confirm (not test-confirm)
4. Verify RS.ge portal shows updated status
5. Verify audit log (is_test_mode=FALSE)

**Rollback:** Set `RSGE_LIVE_ACTIONS_ENABLED=false` (re-deploy)

---

## Monitoring Checklist Per Phase

After each pilot phase:

- [ ] `rsge_actions` — all rows have `action_status=completed`
- [ ] `rsge_actions` — no `response_raw` contains credentials
- [ ] `rsge_documents` / `rsge_waybills` — status updated correctly
- [ ] `rsge_comparison_results` — at least 1 row per document
- [ ] `journal_drafts` — no status changed to `posted` without manual approval
- [ ] Cloud Run logs — no `ACCESS_TOKEN`, `PASSWORD`, `PIN_TOKEN` in log output
- [ ] Cloud Run logs — no `Authorization: bearer` in log output

---

## Escalation Protocol

If any phase fails:

1. Immediately disable the action flag in Cloud Run env vars
2. Record the failing `rsge_actions.id` in incident log
3. Do NOT retry without root cause analysis
4. Do NOT escalate to next phase until current phase passes cleanly

---

## Feature Flag Reference

| Flag | Phase Activated | Purpose |
|---|---|---|
| `RSGE_ALLOW_TEST_ACTIVATE` | 1 | Test waybill activate |
| `RSGE_ALLOW_TEST_CONFIRM` | 2 | Test invoice confirm |
| `RSGE_ALLOW_TEST_REJECT` | 3 | Test reject |
| `RSGE_ALLOW_TEST_CANCEL` | 3 | Test cancel |
| `RSGE_ALLOW_TEST_CORRECT` | 4 | Test correct |
| `RSGE_LIVE_ACTIONS_ENABLED` | 6 | Live production mutations |

---

## Permanently Out of Scope

- Auto-confirm / auto-reject / auto-activate (never batch)
- Balance.ge integration activation
- POSTED_LEDGER_WRITES_ENABLED=true
- H71 payroll tax integration
- Any action without `approved_by` set
