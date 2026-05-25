# Bridge Hub — H70B Controlled Flag Enable Report

**Task:** 11C-H70B  
**Date:** 2026-05-25  
**Type:** Controlled rollout report  
**Author:** Claude (autonomous) — post-execution report  
**Decision:** `H70B_POSTED_LEDGER_WRITES_ENABLED_CONTROLLED_ROLLOUT_PASS`

---

## 1. Authorization

| Item | Value |
|---|---|
| Human sign-off phrase | `CONFIRM_ENABLE_POSTED_LEDGER_WRITES_H70A_NOW` |
| Sign-off document | `docs/h70a-g10-go-no-go-sign-off.md` |
| G1–G9 all PASS | Yes |
| Authorized by | Rolandi Gelikoshvili |

---

## 2. Preflight Checks (before flag enable)

| Check | Result |
|---|---|
| `POSTED_LEDGER_WRITES_ENABLED` absent/false before enable | PASS |
| `Balance.ge` in `demo_mode` | PASS |
| `journal_entry_headers` row count = 0 | PASS |
| G10 sign-off document present | PASS |

---

## 3. Flag Enable

**Command executed:**
```bash
gcloud run services update fastapi-run \
  --update-env-vars="POSTED_LEDGER_WRITES_ENABLED=true" \
  --region europe-west1
```

| Item | Value |
|---|---|
| Cloud Run revision after enable | `fastapi-run-00343-cs7` |
| `POSTED_LEDGER_WRITES_ENABLED` | `true` |
| `Balance.ge` connector | `demo_mode` (unchanged) |

---

## 4. Controlled Posting Test

**Test draft inserted:** `journal_drafts` id=16  
- `tenant_id`: `default`  
- `description`: `H70B controlled ledger write test — automated verify DO NOT USE`  
- `lines_json`: `[{account_code:'1110', debit:1000, credit:0, label:'H70B test DR'}, {account_code:'3100', debit:0, credit:1000, label:'H70B test CR'}]`  
- `connector`: `mock` (not Balance.ge — as required by safety rules)

**Posting call:** `apply_posting_service(draft_id=16, target='mock', tenant_id='default')`

| Item | Value |
|---|---|
| Result | `ok=True` |
| Message | `draft 16 posted to mock` |
| `posting_logs.id` | 54 |
| `erp_id` | `MOCK-16` |
| `posting_logs.status` | `simulated_success` |
| `posting_logs.is_duplicate` | `False` |

---

## 5. Ledger Row Verification

**Header:** `journal_entry_headers`

| Column | Value |
|---|---|
| `id` | `99d02ace-fc56-40e9-8243-5d3a058495c3` |
| `tenant_id` | `default` |
| `entry_date` | `2026-05-25` |
| `period` | `2026-05` |
| `status` | `posted` |
| `source_type` | `journal_draft` |
| `currency` | `GEL` |
| `exchange_rate` | `1.00` |
| `total_debit` | `1000.00` |
| `total_credit` | `1000.00` |
| `posting_log_id` | `NULL` (mock connector does not pass posting_log_id — expected) |
| DR = CR (balanced) | **PASS** |

**Lines:** `journal_entry_lines` (2 rows)

| line_no | account_code | debit | credit |
|---|---|---|---|
| 1 | 1110 | 1000.00 | 0.00 |
| 2 | 3100 | 0.00 | 1000.00 |

**Sources:** `journal_entry_sources` (1 row)

| source_type | source_id |
|---|---|
| `journal_draft` | `16` |

Note: `posting_log` source row absent — expected, because the mock connector does not pass `posting_log_id` in the payload. This is correct behavior; the posting_log_id traceability path requires the connector to forward the log ID explicitly.

---

## 6. Idempotency Check

Re-called `apply_posting_service(draft_id=16, target='mock', tenant_id='default')` after first successful post.

| Check | Result |
|---|---|
| Call returned `ok=False` | PASS — `"journal_drafts id=16 has status=posted for tenant default"` |
| `journal_entry_headers` count unchanged | PASS (1) |
| `journal_entry_lines` count unchanged | PASS (2) |
| `journal_entry_sources` count unchanged | PASS (1) |
| No duplicate ledger rows | **PASS** |

---

## 7. Auth Guard Verification

Tested against live service after flag enable:

| Test | Expected | Result |
|---|---|---|
| Request with no Authorization token | HTTP 401 | **PASS** |
| Request with malformed token | HTTP 401 | **PASS** |
| `/health` (no auth required) | HTTP 200 | **PASS** |

---

## 8. Rollback Trigger Checks

| Trigger | Status |
|---|---|
| `Balance.ge` still `demo_mode` | PASS — confirmed via `/health` |
| No 5xx errors observed | PASS |
| No unbalanced ledger entries (DR ≠ CR) | PASS — single entry: DR=CR=1000 |
| `BALANCE_API_KEY` unchanged | PASS — not touched |
| H71 not started | PASS — no H71 work initiated |
| No secrets exposed | PASS |
| `POSTED_LEDGER_WRITES_ENABLED` correctly `true` | PASS — revision `fastapi-run-00343-cs7` |

---

## 9. Summary

The controlled rollout of `POSTED_LEDGER_WRITES_ENABLED=true` completed successfully:

1. Flag enabled → revision `fastapi-run-00343-cs7`
2. One controlled mock posting executed → `log_id=54`, `erp_id=MOCK-16`
3. Ledger rows created: 1 header (balanced), 2 lines, 1 source row
4. Idempotency verified: no duplicate rows on retry
5. Auth guards intact: 401 on unauthenticated requests
6. Balance.ge remains `demo_mode`: no live ERP traffic
7. Zero rollback triggers fired

---

## 10. Decision

**`H70B_POSTED_LEDGER_WRITES_ENABLED_CONTROLLED_ROLLOUT_PASS`**

*Bridge Hub — Task 11C-H70B. POSTED_LEDGER_WRITES_ENABLED=true live in revision fastapi-run-00343-cs7. Ledger writes active. Balance.ge protected (demo_mode). All rollback triggers clear.*
