# RS.ge Connector Architecture

## Overview

Bridge Hub RS.ge connector provides a unified interface to two RS.ge APIs:
- **SOAP WayBill API** — for waybills (ზედნადები)
- **eAPI REST** — for tax invoices (საგადასახადო ფაქტურები) via RSoAuth v3

Both APIs are wrapped in `app/api/connectors/rs_ge_connector.py`.

---

## Connection Modes

| Mode | Description |
|---|---|
| `demo` | No RS.ge credentials; returns mock responses |
| `live` | Real RS.ge credentials; connects to RS.ge |

Mode is determined at connector init: if credentials are present (from vault or env), mode=`live`.

---

## Authentication

### SOAP (WayBill API)
1. `start_soap_auth(conn, tenant_id, su, sp)` — stores credentials in vault, verifies with `GetUserInfo`
2. No PIN step for SOAP; single-step

### eAPI (RSoAuth v3) — 2-step
1. `start_eapi_auth(conn, tenant_id, public_key, secret_key)`:
   - One-step: returns `{"connected": True, "steps": 1}`
   - Two-step: returns `{"connected": False, "steps": 2, "pin_token": "...", "masked_mobile": "..."}`
2. `verify_pin(conn, tenant_id, pin_token, pin_code)` — exchanges PIN for ACCESS_TOKEN
3. Token stored in vault via `vault_store_token(conn, tenant_id, token)`
4. Token NEVER returned in API response

---

## Credential Security

- Credentials stored in `credential_vault` table via `CredentialVaultService`
- Encrypted at rest with `VAULT_ENCRYPTION_KEY`
- Routes call `load_connector_creds()` (public wrapper) — not `get_decrypted_soap_creds()` directly
- No credential in frontend, logs, or API responses
- `_mask(su)` helper shows only first 2 + last 2 chars

---

## SOAP Transport

```python
_soap_call(wsdl_url, method_name, namespace, params) → XML Element
```

- Uses `zeep` or `requests` with manual SOAP envelope
- Parses XML response with `xml.etree.ElementTree`
- `_xml_text(element, tag)` — safe text extraction
- `_result_xml(root, result_tag)` — extracts result element

### Key WSDLs
- `_WAYBILL_WSDL` — WayBill SOAP endpoint
- `_INVOICE_WSDL` — Invoice SOAP endpoint
- `_WB_NS`, `_INV_NS` — namespaces

---

## eAPI REST Transport

- `GET/POST https://eapi.rs.ge/...` with `Authorization: Bearer {token}`
- Token loaded from vault per-request
- Authorization header NEVER logged

---

## Connector Methods

| Method | API | Purpose |
|---|---|---|
| `get_waybill(id)` | SOAP | Fetch single waybill |
| `get_waybill_by_number(num)` | SOAP | Fetch by waybill number |
| `get_buyer_waybills(...)` | SOAP | List received waybills (STATUS=-100 limitation) |
| `post(draft)` | SOAP | Submit waybill to RS.ge |
| `cancel_waybill(id)` | SOAP | Cancel waybill |
| `get_user_invoices(limit)` | eAPI | List tax invoices |
| `get_invoice_by_id(id)` | eAPI | Fetch invoice detail |
| `save_invoice(draft)` | eAPI | Submit invoice |
| `verify_taxpayer(inn)` | REST | Verify taxpayer INN |
| `get_waybill_types()` | SOAP | Lookup table |
| `get_waybill_units()` | SOAP | Lookup table |
| `preview(draft)` | Local | Validate without submitting |

---

## Known Limitation: STATUS=-100

`get_buyer_waybills` returns STATUS=-100 for the current service user because buyer-side authorization is not configured in RS.ge for this credential. Goods details are also blocked.

**Workaround:** Users enter waybill numbers manually; single-number sync via `GET /rs-ge/waybill/by-number/{num}`.
