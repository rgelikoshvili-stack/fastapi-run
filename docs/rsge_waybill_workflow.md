# RS.ge — Waybill (ზედნადები) Workflow

## Overview

RS.ge ზედნადები are goods transportation documents. Bridge Hub supports:
- Syncing received (incoming) waybills by number
- Creating accounting entries from waybills
- VAT-split draft creation
- Partner/item mapping for auto Dr/Cr suggestion
- Test-mode activate/cancel

---

## STATUS=-100 Limitation

`get_buyer_waybills` SOAP returns STATUS=-100 for the current service user — buyer-side authorization not configured for service account in RS.ge. Goods details are also blocked.

**Impact:** Period-based received waybill listing does not work automatically.

**Workaround:**
1. User views waybill numbers on RS.ge portal
2. Enters numbers in Bridge Hub "მიღ. ζεδ. ნომ." field
3. Clicks "ჩამოტვ." for single or "ყველა" for batch

---

## Sync Flow

### Single by number
```
Input: waybill_number = "0997264809"
→ GET /rs-ge/waybill/by-number/{number}
→ SOAP call: get_waybill_by_number(num)
→ Upsert to rsge_waybills
```

### By rsge_id
```
POST /rs-ge/waybills/sync-selected
{"rsge_ids": ["12345"]}
```

---

## Data Stored

`rsge_waybills`:
- waybill_number, rsge_id
- buyer_tin, buyer_name
- seller_tin, seller_name (added via ALTER)
- full_amount, begin_date
- raw_payload (JSONB) — goods_list from SOAP
- draft_id, draft_status
- evidence_id

---

## Edit Meta (Local Override)

When SOAP returns partial data:
```
PATCH /rs-ge/waybills/{id}/edit-meta
{
  "begin_date": "2025-01-15",
  "full_amount": 1180.0,
  "goods_list": [{"name": "საქ.", "quantity": 2, "amount": 1180.0, "code": "BAR001"}]
}
```
Saved to `raw_payload` and waybill columns. Does not affect RS.ge.

---

## Accounting Draft (VAT Split)

```
POST /rs-ge/waybills/{id}/create-draft
{
  "debit_account": "1310",
  "credit_account": "3110",
  "vat_split": true,
  "vat_rate": 18.0
}
```

With `vat_split=true` creates 3-line journal:
```
Dr 1310  (net amount)
Dr 3311  (VAT 18%)
Cr 3110  (total amount)
```

---

## Partner + Item Mapping

"📌 მარ." button saves `seller_tin → Cr account` to `rsge_partner_map`.
Auto-suggest fires on waybill expand:
```
POST /rs-ge/suggest-draft
{"seller_tin": "405176367", "goods_list": [...]}
→ {"credit_account": "3110", "debit_account": "1310", "source": "both_maps"}
```

---

## Waybill vs Invoice Comparison

```
GET  /rs-ge/waybills/{id}/compare
POST /rs-ge/waybills/{id}/compare-and-store
```

Compares:
- `full_amount` vs linked invoice `TOTAL`
- waybill goods vs invoice lines (by OVERHEAD_NO match)
- Returns: matched | amount_mismatch | line_mismatch | missing_in_bridge

---

## Test-Mode Actions

```
POST /rs-ge/waybills/{id}/preview-activate
POST /rs-ge/waybills/{id}/test-activate   {"approved_by": "user_id"}
POST /rs-ge/waybills/{id}/preview-cancel
POST /rs-ge/waybills/{id}/test-cancel     {"approved_by": "user_id"}
```

Requirements:
- RSGE_TEST_MODE=true
- RSGE_ALLOW_TEST_ACTIVATE=true / RSGE_ALLOW_TEST_CANCEL=true
- RBAC: posting:write
- approved_by required
- Audit written before + after

---

## UI Workbench (rsge-sync.html v6)

- Period filter → "RS.ge-დან ჩამ." button
- Manual number input (single + batch)
- Expandable rows: seller, date, goods grid, Dr/Cr inputs
- VAT 18% checkbox with preview
- Save Meta button (date + goods edits)
- "📌 მარ." button → partner map
- Auto-suggest badge next to Dr/Cr
- Settings tab: own TIN, partner map list, item map list
