# RS.ge — Invoice / Tax Document Workflow

## Document Types

| RS.ge type | Bridge Hub doc_type | Direction |
|---|---|---|
| საგადასახადო ფაქტურა | invoice | incoming or outgoing |
| კორექტირება | correction | links original invoice |
| გაუქმება | cancellation | links original invoice |

---

## Sync Flow

### 1. List available invoices
```
GET /rs-ge/invoices?limit=50
```
Returns live RS.ge invoice list via eAPI.

### 2. Sync selected to local DB
```
POST /rs-ge/documents/sync-selected
{"rsge_ids": ["100", "101"], "own_inn": "405176367"}
```
- Upserts to `rsge_documents` by (tenant_id, rsge_id)
- Sets direction: incoming/outgoing/unknown
- Stores source_hash for dedup

### 3. Create evidence
```
POST /rs-ge/documents/{id}/create-evidence
```
- Creates record in `documents` table (Bridge Hub evidence)
- Idempotent: returns existing evidence_id if already created

### 4. Create accounting draft
```
POST /rs-ge/documents/{id}/create-draft
{"own_inn": "405176367"}
```
- Auto-detects own_inn from `tenant_settings` if not provided
- Creates `journal_drafts` record with Dr/Cr suggestion
- Returns draft_id for approval flow

### 5. Compare vs internal state
```
GET /rs-ge/documents/{id}/compare?target=evidence
GET /rs-ge/documents/{id}/compare?target=journal_draft
GET /rs-ge/documents/{id}/compare?target=posted_ledger
```

### 6. Test-mode actions
```
POST /rs-ge/documents/{id}/preview-confirm
POST /rs-ge/documents/{id}/test-confirm   {"approved_by": "user_id"}
```
All blocked in production until feature flags enabled.

---

## Status Codes (RS.ge SOAP)

| Code | Meaning |
|---|---|
| 0 | Saved (draft) |
| 1 | Confirmed |
| 2 | Rejected |
| 3 | Cancelled |
| 5 | Corrected |
| -1 | Deleted |

---

## Evidence Structure

```json
{
  "document_type": "invoice",
  "source": "rs.ge",
  "rsge_id": "12345",
  "reg_no": "INV-001",
  "seller_inn": "405176367",
  "direction": "incoming",
  "rsge_status": "1",
  "vat_amount": 180.0
}
```

---

## Linked Waybill

RS.ge invoices carry `OVERHEAD_NO` field = linked waybill number.
`GET /rs-ge/waybills/{id}/linked-invoice` finds this link.
`rsge_documents.waybill_number` stores it for index lookup.

---

## Correction / Cancellation Drafts

When a document is corrected or cancelled:
```
POST /rs-ge/documents/{id}/create-correction-draft
POST /rs-ge/documents/{id}/create-reversal-draft
```
Creates reversal suggestion with confidence=0.70.
Accountant reviews before approval.
