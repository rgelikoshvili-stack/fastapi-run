# RS.ge — Document Comparison and Matching

## Purpose

Georgian accounting requires verifying that RS.ge documents match internal accounting records. Bridge Hub implements structured comparison similar to 1C reconciliation — comparing RS.ge source documents against Bridge Hub evidence, drafts, and posted entries.

---

## Comparison Service

`app/api/services/rsge_comparison_service.py`

### Comparison Types

| Compare Target | Endpoint | What is checked |
|---|---|---|
| Evidence | `/documents/{id}/compare?target=evidence` | amount, VAT |
| Journal Draft | `/documents/{id}/compare?target=journal_draft` | amount |
| Posted Ledger | `/documents/{id}/compare?target=posted_ledger` | amount, posted status |
| Waybill vs Invoice | `/waybills/{id}/compare` | amount, goods vs lines |

---

## Comparison Statuses

| Status | Meaning |
|---|---|
| `matched` | All fields within tolerance |
| `amount_mismatch` | Amount differs > 0.02 GEL |
| `vat_mismatch` | VAT differs > 0.05 GEL |
| `seller_buyer_mismatch` | Buyer/seller INN differs |
| `line_mismatch` | Invoice has lines not on waybill |
| `product_unmapped` | Goods code not in item_map |
| `missing_in_bridge` | No evidence/draft in Bridge Hub |
| `missing_in_rsge` | Doc in Bridge Hub but not on RS.ge |
| `duplicate` | Same source_hash already synced |
| `requires_review` | Uncertain — manual review needed |

---

## Risk Levels

| Risk | Triggers |
|---|---|
| `low` | Matched |
| `medium` | amount_mismatch, vat_mismatch, line_mismatch |
| `high` | seller_buyer_mismatch, duplicate, missing |

---

## Tolerances

```python
AMOUNT_TOLERANCE = Decimal("0.02")  # 2 tetri
VAT_TOLERANCE    = Decimal("0.05")  # 5 tetri
```

---

## Compare and Store

`POST /rs-ge/documents/{id}/compare-and-store`

Runs comparison and persists result to `rsge_comparison_results`:

```json
{
  "comparison_status": "amount_mismatch",
  "amount_diff": 0.50,
  "risk_level": "medium",
  "mismatch_summary": "თანხა: RS.ge=1180.00 ≠ ევ.=1179.50",
  "comparison_result_id": 42
}
```

---

## rsge_comparison_results Table

| Column | Purpose |
|---|---|
| rsge_document_id | Source RS.ge document |
| rsge_waybill_id | Source waybill (nullable) |
| compare_target_type | evidence / journal_draft / posted_ledger / invoice |
| compare_target_id | Bridge Hub record ID |
| comparison_status | See status table above |
| amount_diff / vat_diff | Numeric difference |
| line_diff_count | Extra lines on invoice |
| diff_lines | JSONB — extra invoice lines |
| risk_level | low / medium / high |
| mismatch_summary | Human-readable description |
| reviewed_by | Bridge Hub user who reviewed |

---

## Product Mapping Check

```python
await check_product_mapping(conn, tenant_id, goods_list)
→ {"status": "product_unmapped", "unmapped": ["BAR001"], "mapped": ["CODE2"]}
```

Used to flag items without Dr account mapping.

---

## Deduplication

`source_hash` field on `rsge_documents`:
```python
key = f"{rsge_id}|{reg_no}|{amount}|{status_code}"
hash = sha256(key)[:32]
```
ON CONFLICT (tenant_id, rsge_id) DO UPDATE — safe to sync repeatedly.
