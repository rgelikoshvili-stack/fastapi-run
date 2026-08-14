# RS.ge Integration — Current State Audit

**Date:** 2026-08-13  
**Version:** RS-3 Gap Closure  
**Auditor:** Bridge Hub Engineering

---

## Overview

Bridge Hub RS.ge integration provides 1C/Balance-style accounting workflow connected to RS.ge (Georgian Revenue Service portal). This audit covers what is implemented, what gaps existed, and what was closed in RS-3.

---

## Infrastructure Summary

| Component | Status | File |
|---|---|---|
| SOAP WayBill connector | ✅ | `app/api/connectors/rs_ge_connector.py` |
| eAPI REST connector | ✅ | `app/api/connectors/rs_ge_connector.py` |
| SOAP auth (2-step) | ✅ | `app/api/services/rsge_auth_service.py` |
| eAPI auth (RSoAuth v3) | ✅ | `app/api/services/rsge_auth_service.py` |
| Document sync service | ✅ | `app/api/services/rsge_document_service.py` |
| Waybill sync service | ✅ | `app/api/services/rsge_waybill_service.py` |
| Action service (test mode) | ✅ | `app/api/services/rsge_action_service.py` |
| Comparison service | ✅ RS-3 | `app/api/services/rsge_comparison_service.py` |
| Feature flags | ✅ | `app/api/services/rsge_config.py` |
| Submission service | ✅ | `app/api/services/rsge_submission_service.py` |
| Route handlers (43+) | ✅ | `app/api/routes_rs_ge.py` |
| Frontend workbench (v6) | ✅ | `static/rsge-sync.html` |

---

## DB Schema

| Table | Status |
|---|---|
| rsge_credentials | ✅ |
| rsge_sync_jobs | ✅ |
| rsge_documents | ✅ |
| rsge_document_lines | ✅ |
| rsge_document_status_history | ✅ |
| rsge_waybills | ✅ |
| rsge_actions | ✅ |
| rsge_taxpayer_cache | ✅ |
| rsge_partner_map | ✅ |
| rsge_item_map | ✅ |
| rsge_comparison_results | ✅ RS-3 |

---

## Endpoints (RS-3 state)

### Auth
- `POST /rs-ge/auth/start` — SOAP 2-step initiate
- `POST /rs-ge/auth/verify-pin` — PIN verification
- `POST /rs-ge/auth/signout` — Sign out
- `GET  /rs-ge/auth/status` — Connection status

### Documents (Invoices)
- `GET  /rs-ge/documents` — List from RS.ge
- `GET  /rs-ge/documents/{id}` — Get single
- `POST /rs-ge/documents/sync-selected` — Sync to local DB
- `POST /rs-ge/documents/{id}/create-evidence` — Create evidence
- `POST /rs-ge/documents/{id}/create-draft` — Create accounting draft
- `POST /rs-ge/documents/{id}/create-correction-draft` — ✅ RS-3
- `POST /rs-ge/documents/{id}/create-reversal-draft` — ✅ RS-3
- `GET  /rs-ge/documents/{id}/compare` — ✅ RS-3
- `POST /rs-ge/documents/{id}/compare-and-store` — ✅ RS-3
- `POST /rs-ge/documents/{id}/preview-confirm` — Test mode
- `POST /rs-ge/documents/{id}/test-confirm` — Test mode
- `POST /rs-ge/documents/{id}/preview-reject` — Test mode
- `POST /rs-ge/documents/{id}/test-reject` — Test mode
- `POST /rs-ge/documents/{id}/preview-correct` — Test mode
- `POST /rs-ge/documents/{id}/test-correct` — Test mode
- `POST /rs-ge/documents/{id}/preview-cancel` — Test mode
- `POST /rs-ge/documents/{id}/test-cancel` — Test mode

### Waybills
- `GET  /rs-ge/waybills` — List synced
- `POST /rs-ge/waybills/sync` — Sync by period
- `GET  /rs-ge/waybills/{id}/goods` — Goods list
- `POST /rs-ge/waybills/{id}/create-evidence` — Create evidence
- `POST /rs-ge/waybills/{id}/create-draft` — Accounting draft (VAT-split)
- `PATCH /rs-ge/waybills/{id}/edit-meta` — Edit local date/goods
- `GET  /rs-ge/waybills/{id}/linked-invoice` — Find linked invoice
- `GET  /rs-ge/waybills/{id}/compare` — ✅ RS-3
- `POST /rs-ge/waybills/{id}/compare-and-store` — ✅ RS-3
- `POST /rs-ge/waybills/{id}/preview-activate` — Test mode
- `POST /rs-ge/waybills/{id}/test-activate` — Test mode
- `POST /rs-ge/waybills/{id}/preview-cancel` — Test mode
- `POST /rs-ge/waybills/{id}/test-cancel` — Test mode

### Mapping & Settings
- `GET/POST/DELETE /rs-ge/partner-map` — Seller TIN → Cr account
- `GET/POST/DELETE /rs-ge/item-map` — Item code → Dr account
- `POST /rs-ge/suggest-draft` — Auto-suggest Dr/Cr from mappings
- `GET/POST /rs-ge/own-tin` — ✅ RS-3 Company own TIN setting

### Comparison
- `GET/POST /rs-ge/comparison-results` — ✅ RS-3 Structured comparison history

---

## Feature Flags

| Flag | Default | Purpose |
|---|---|---|
| RSGE_ENABLED | false | Global enable |
| RSGE_READ_ONLY | true | Block mutations |
| RSGE_TEST_MODE | false | Allow test actions |
| RSGE_LIVE_ACTIONS_ENABLED | false | Block all live mutations |
| RSGE_ALLOW_TEST_CONFIRM | false | Allow test-confirm |
| RSGE_ALLOW_TEST_REJECT | false | Allow test-reject |
| RSGE_ALLOW_TEST_CORRECT | false | Allow test-correct |
| RSGE_ALLOW_TEST_CANCEL | false | Allow test-cancel |
| RSGE_ALLOW_TEST_ACTIVATE | false | Allow test-activate |

---

## Test Suite

21 unit test files, 246+ test cases. All pass.

---

## Known Limitations

1. `get_buyer_waybills` SOAP returns STATUS=-100 for current credential — received waybills cannot be auto-listed by period. Workaround: manual number entry.
2. Goods details blocked for received waybills (STATUS=-100). Manual entry required.
3. Customs declarations API: not yet implemented.
4. RS.ge employee connector: not yet implemented.
5. Modular `connectors/rsge/` subdirectory: single-file implementation.
