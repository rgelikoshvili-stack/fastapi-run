# RS.ge — Accounting Software Workflow (1C/Balance Style)

## Goal

Bridge Hub operates as a Georgian accounting program connected to RS.ge, similar to how 1C:Enterprise or Balance.ge work — documents from RS.ge are downloaded, classified, reviewed, and booked into the accounting ledger through an approval workflow.

---

## Core Workflow (Purchase Flow)

```
RS.ge Portal
     │
     ▼
[1] SYNC — download waybill/invoice by number or period
     │
     ▼
[2] EVIDENCE — create internal document record (rsge_documents / rsge_waybills)
     │
     ▼
[3] COMPARE — compare RS.ge document vs Bridge Hub state
     │         (amount, VAT, lines, seller/buyer)
     ▼
[4] CLASSIFY — auto-detect direction (purchase/sale) using own TIN
     │         buyer_inn == own → incoming purchase
     │         seller_inn == own → outgoing sale
     ▼
[5] DRAFT — create accounting journal draft (Dr/Cr suggestion)
     │       VAT split: Dr1310(net) + Dr3311(VAT) / Cr3110(total)
     │       mapped via partner_map + item_map
     ▼
[6] REVIEW — accountant reviews draft in Bridge Hub
     │        can edit accounts, amounts, date
     ▼
[7] APPROVE — CFO/admin approves (single or dual approval)
     │
     ▼
[8] POST — journal entry posted to ledger
```

---

## Own TIN Auto-Detection

Set via `POST /rs-ge/own-tin`:
```json
{"tin": "405176367"}
```

Then for each synced document:
- `buyer_inn == own_tin` → direction = `incoming` (purchase)
- `seller_inn == own_tin` → direction = `outgoing` (sale)
- both match → `conflict_requires_review`
- neither matches → `unknown_requires_review`
- no own TIN set → `company_identity_missing`

---

## VAT Split (18%)

When `vat_split=true` on draft creation:
```
total = 1180 ₾
VAT   = 1180 × 18/118 = 180 ₾
net   = 1000 ₾

Dr 1310  1000  (goods/inventory)
Dr 3311   180  (input VAT)
Cr 3110  1180  (accounts payable)
```

---

## Partner and Item Mapping

- **Partner Map:** `seller_tin → credit_account` (Cr)
  - Stored in `rsge_partner_map`
  - Set via "📌 მარ." button on waybill or Settings tab
- **Item Map:** `bar_code/product_code → debit_account` (Dr)
  - Stored in `rsge_item_map`
  - Set via Settings tab

Auto-suggest fires on each waybill expand and pre-fills Dr/Cr if mappings exist.

---

## Correction and Cancellation

- `POST /rs-ge/documents/{id}/create-correction-draft` — suggests correction entry
- `POST /rs-ge/documents/{id}/create-reversal-draft` — suggests reversal for cancelled doc
- Both create `status='drafted'` — no auto-posting
- Accountant reviews and approves before posting

---

## Safety Invariants

1. No RS.ge live mutation without RSGE_LIVE_ACTIONS_ENABLED=true + all 9 safety flags
2. No auto-posting of accounting entries
3. No auto-approval of drafts
4. Balance.ge not activated
5. POSTED_LEDGER_WRITES_ENABLED not changed
