# Bridge Hub — Report UI/API Drill-down Test Results

## 1. Purpose

Task 11C-H17 verifies that posted-ledger report rows expose a safe and complete
drill-down chain from report total to audit evidence, using local in-memory
fixture payloads only.  No DB connections, no network calls, no SQL, no
migrations.  Production default behavior is unchanged.

---

## 2. Safety Scope

| Constraint | Status |
|---|---|
| No production DB | confirmed |
| No Cloud Run DB | confirmed |
| No SQL execution | confirmed |
| No migration execution | confirmed |
| No DB connection | confirmed |
| No Balance.ge activation | confirmed |
| No credentials changed | confirmed |
| No connector behavior changed | confirmed |
| No infrastructure changed | confirmed |
| Production feature flag (`POSTED_LEDGER_REPORTS_ENABLED`) remains OFF | confirmed |
| No runtime report behavior changed | confirmed — tests/docs only |
| No posting behavior changed | confirmed |
| No approval logic changed | confirmed |
| No UI/static files changed | confirmed |

---

## 3. Drill-down Chain Verified

```
report total / report row
  → ledger line         (ledger_line_id)
  → journal entry header (journal_entry_id)
  → source draft         (source_draft_id)
  → posting log          (posting_log_id)
  → evidence bundle      (evidence_bundle_id — nullable)
  → audit/evidence trail (audit_event_id)
```

Each link was verified using local fixture payloads in
`tests/unit/test_report_ui_api_drilldown_contract.py`.

---

## 4. Payload Fields Verified

| Field | Required | Nullable |
|---|---|---|
| `tenant_id` | yes | no |
| `report_type` | yes | no |
| `ledger_line_id` | yes | no |
| `journal_entry_id` | yes | no |
| `source_draft_id` | yes | no |
| `posting_log_id` | yes | no |
| `evidence_bundle_id` | yes | yes (nullable) |
| `account_code` | yes | no |
| `account_type` | yes | no |
| `counterparty_id` | yes | yes |
| `document_id` | yes | yes |
| `correction_of_id` | yes | yes |
| `reversal_of_id` | yes | yes |
| `audit_event_id` | yes | yes |
| `drilldown_available` | yes | no (bool) |

---

## 5. UI/API Actions Verified

The drill-down response payload must include an `actions` list containing:

| Action | Purpose |
|---|---|
| `view_ledger_line` | Navigate to the individual ledger movement |
| `view_journal_entry` | Navigate to the full journal entry header |
| `view_evidence_bundle` | Navigate to the attached evidence bundle |
| `view_posting_log` | Navigate to the ERP posting log |

All four actions verified in tests 24–27.

---

## 6. Security / Privacy

| Property | Verified |
|---|---|
| Tenant isolation — all rows scoped to correct `tenant_id` | yes (test 15) |
| Cross-tenant rows filtered before response | yes (test 16) |
| `view_*` actions gated by 401/403 without auth | yes (test 28) |
| Raw secrets (`api_key`, `password`, `token`, etc.) forbidden in all payloads | yes (test 23) |
| No silent fallback to `journal_drafts` | yes (test 31) |
| `_assert_no_silent_fallback` raises on any `journal_drafts` reference | yes |
| Missing `tenant_id` fails closed (`ValueError`) | yes (test 29) |
| Feature flag keeps drill-down behind `POSTED_LEDGER_REPORTS_ENABLED` | yes (test 30) |

---

## 7. Reversal / Correction Chain

- **Standard view** (test 20): only `STANDARD_NET_STATUSES` (`posted`, `correction`) rows included; `reversed` rows excluded.
- **History view** (test 21): all statuses present (`posted`, `correction`, `reversed`); `reversal_of_id` links reversal entry back to the original.
- `correction_of_id` field present on all detail rows; set where applicable.

---

## 8. Test Results

| Suite | Command | Result |
|---|---|---|
| H17 targeted | `pytest tests/unit/test_report_ui_api_drilldown_contract.py -v` | **34 passed** |
| H16 + H17 | both fixture verification files | **58 passed** |
| Related contract suite (H1–H17, 19 files) | all listed files | **1296 passed** |
| Full unit suite | `pytest tests/unit/` | **3797 passed, 2 skipped** |

All runs: 0 failed, 5 deprecation warnings (SwigPy — unrelated to project code).

---

## 9. Non-goals

This task does **not**:

- Switch production to posted-ledger reports (`POSTED_LEDGER_REPORTS_ENABLED` stays unset)
- Run any real DB migration
- Activate Balance.ge or any ERP connector
- Change posting service logic
- Change approval service logic
- Implement UI/static pages (contract only — no HTML/JS changes)
- Start H18

---

## 10. Next Task

Only after PR merge, deploy to Cloud Run, and live HTTP verification:

**11C-H18 — Controlled Non-Production Runtime Switch**
