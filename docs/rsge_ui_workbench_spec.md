# RS.ge — UI Workbench Spec (rsge-sync.html v6)

## File Location

`static/rsge-sync.html`

Served at: `{base_url}/static/rsge-sync.html`

---

## Tab Structure

```
[ ζεδ. (Waybills) | ფ-ა (Invoices) | ➕ ახ. (New) | პარამ. (Settings) ]
```

### Tab 1 — ζεδ. (Waybills) — `pane-waybills`

**Sync Panel:**
- Tenant dropdown
- Period from/to date inputs
- "RS.ge-დან ჩამ." button (sync by period — hits GET /rs-ge/waybills)
- Manual number input + "ჩამოტვ." (single sync by number)
- "ყველა" (batch sync selected)

**Waybill Table:**
- Columns: ☐ | # | ζεδ.ნომ. | გამყ. | თარ. | თანხა | სტ. | 📌
- Expandable row → shows seller, goods grid, Dr/Cr inputs
- VAT 18% checkbox with live preview (net / VAT / total)
- Auto-suggest badge: shows "→ Dr1310 / Cr3110" if map found
- "📌 მარ." button → saves seller TIN → Cr account to partner_map
- "Save Meta" button → saves local date/goods override
- "Ჩ/ე" (create-draft) button → POST /rs-ge/waybills/{id}/create-draft
- "შ-ბ" (create-evidence) button → POST /rs-ge/waybills/{id}/create-evidence

### Tab 2 — ფ-ა (Invoices) — `pane-invoices`

**Sync Panel:**
- "RS.ge-დან" button → GET /rs-ge/invoices (list)
- Checkboxes to select invoices for sync

**Invoice Table:**
- Columns: ☐ | reg_no | გამყ. | მყ. | თარ. | თანხა | დღგ | მიმ. | სტ.
- Expandable row → full invoice details
- "სინქ." (sync-selected) → POST /rs-ge/documents/sync-selected
- "ევ." (evidence) → POST /rs-ge/documents/{id}/create-evidence
- "ნ/ე" (draft) → POST /rs-ge/documents/{id}/create-draft

### Tab 3 — ➕ ახ. (New) — `pane-new`

Manual waybill entry form:
- Fields: waybill_number, seller_tin, buyer_tin, full_amount, begin_date, goods (JSONB textarea)
- "შექმ." (create) → POST /rs-ge/waybills

### Tab 4 — პარამ. (Settings) — `pane-settings`

**Own TIN Card:**
```
[ საკ.სა.ნომ. input field ]  [ Save ]  [ status text ]
GET  /rs-ge/own-tin
POST /rs-ge/own-tin {"tin": "..."}
```

**Partner Map List:**
```
TIN               → Account    [✕]
405176367         → 3110       [✕]
```
DELETE /rs-ge/partner-map/{id}

**Item Map List:**
```
Code              → Account    [✕]
BAR001            → 1310       [✕]
```
DELETE /rs-ge/item-map/{id}

---

## API Calls Used

| Action | Method | Endpoint |
|---|---|---|
| List waybills | GET | /rs-ge/waybills |
| Sync by number | GET | /rs-ge/waybill/by-number/{num} |
| Sync selected | POST | /rs-ge/waybills/sync-selected |
| Create evidence | POST | /rs-ge/waybills/{id}/create-evidence |
| Create draft | POST | /rs-ge/waybills/{id}/create-draft |
| Save meta | PATCH | /rs-ge/waybills/{id}/edit-meta |
| Suggest draft | POST | /rs-ge/suggest-draft |
| Save partner map | POST | /rs-ge/partner-map |
| Delete partner map | DELETE | /rs-ge/partner-map/{id} |
| Own TIN get | GET | /rs-ge/own-tin |
| Own TIN set | POST | /rs-ge/own-tin |
| Item map list | GET | /rs-ge/item-map |
| Delete item map | DELETE | /rs-ge/item-map/{id} |
| List invoices | GET | /rs-ge/invoices |
| Sync invoices | POST | /rs-ge/documents/sync-selected |
| Preview action | POST | /rs-ge/documents/{id}/preview-{action} |
| Test action | POST | /rs-ge/documents/{id}/test-{action} |

---

## JS Function Map

```javascript
switchTab(tabId)          // switches visible pane
loadWaybills()            // GET /rs-ge/waybills
syncByNumber()            // GET /rs-ge/waybill/by-number/{num}
expandWaybill(id)         // toggle row, load details, fire suggest-draft
saveWaybillMeta(id)       // PATCH edit-meta
savePartnerMap(id, tin)   // POST /rs-ge/partner-map
createDraft(id)           // POST /rs-ge/waybills/{id}/create-draft
createEvidence(id)        // POST /rs-ge/waybills/{id}/create-evidence
loadInvoices()            // GET /rs-ge/invoices
syncSelectedInvoices()    // POST /rs-ge/documents/sync-selected
loadSettingsTab()         // loads all 3 settings sections
saveOwnTin()              // POST /rs-ge/own-tin
loadPartnerMap()          // GET /rs-ge/partner-map
deletePartnerMap(id)      // DELETE /rs-ge/partner-map/{id}
loadItemMap()             // GET /rs-ge/item-map
deleteItemMap(id)         // DELETE /rs-ge/item-map/{id}
```

---

## UI State Machine

```
Waybill row: [synced] → [expanded] → [draft_created] → [evidence_created] → [approved]
Invoice row: [synced] → [evidence_created] → [draft_created] → [approved]
```

Badge colors:
- Gray → not processed
- Yellow → draft created
- Green → evidence + draft + approved
- Red → comparison mismatch

---

## Security Notes

- Bearer token stored in `localStorage.getItem("bh_token")` — not in URL params
- No RS.ge credentials in browser at any time
- Test-mode action buttons disabled unless RSGE_TEST_MODE flag visible in config
