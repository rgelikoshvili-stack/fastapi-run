# Bridge Hub BIZ-1 — GeoTrade RS.ge Workflow Documentation

**Task:** BIZ-1 Phase 4, 20  
**Safety:** FIXTURE ONLY. No real RS.ge calls. No production credentials.

---

## RS.ge Document Lifecycle in Bridge Hub

```
RS.ge API (mock)
    │
    ▼
rsge_document_service.py / rsge_waybill_service.py
    │  (sync, deduplicate)
    ▼
Evidence (rsge_source)
    │
    ▼
Direction Detection
    ├─ buyer_inn == own_inn → incoming (purchase)
    ├─ seller_inn == own_inn → outgoing (sale)
    ├─ both match → conflict_requires_review
    └─ neither → unknown_requires_review
    │
    ▼
Draft Journal Entry (not auto-posted)
    │
    ▼
Approval (accountant/admin)
    │
    ▼
Posted Ledger Entry
```

---

## GeoTrade RS.ge Fixtures

### Incoming Documents (Purchases)
| ID | Supplier | Net | VAT | Gross | Direction |
|----|---------|-----|-----|-------|-----------|
| RS-INV-PUR-001 | Office Supplier LLC | 5,000 | 900 | 5,900 | incoming |
| RS-INV-RENT-001 | Rent House LLC | 1,000 | 180 | 1,180 | incoming |
| RS-INV-FA-001 | Tech House LLC | 3,000 | 540 | 3,540 | incoming |

### Outgoing Documents (Sales)
| ID | Customer | Net | VAT | Gross | Direction |
|----|---------|-----|-----|-------|-----------|
| RS-INV-SALE-001 | Client LTD | 1,600 | 288 | 1,888 | outgoing |

### Mismatch Test Documents
| ID | Type | Risk |
|----|------|------|
| RS-INV-MISMATCH-001 | missing_in_bridge | RISK_HIGH |
| RS-INV-AMOUNT-MISMATCH-001 | amount_mismatch | RISK_MEDIUM |

---

## RS.ge Waybill Fixtures

| ID | Type | Linked Invoice | Mismatch |
|----|------|---------------|---------|
| RS-WB-PUR-001 | incoming | RS-INV-PUR-001 | None (matched) |
| RS-WB-SALE-001 | outgoing | RS-INV-SALE-001 | None (matched) |
| RS-WB-UNLINKED-001 | incoming | None | waybill_invoice_unlinked |

---

## Mismatch Types (rsge_comparison_service.py)

| Constant | Meaning | Risk Default |
|----------|---------|-------------|
| `MATCHED` | Documents match | RISK_LOW |
| `AMOUNT_MISMATCH` | Amount differs > tolerance | RISK_MEDIUM |
| `VAT_MISMATCH` | VAT differs > tolerance | RISK_MEDIUM |
| `SELLER_BUYER_MISMATCH` | INN doesn't match | RISK_HIGH |
| `MISSING_IN_BRIDGE` | RS.ge doc without Bridge Hub evidence | RISK_HIGH |
| `MISSING_IN_RSGE` | Bridge Hub draft without RS.ge source | RISK_MEDIUM |
| `DUPLICATE` | Same RS.ge doc appears twice | RISK_HIGH |
| `REQUIRES_REVIEW` | Needs manual verification | RISK_MEDIUM |
| `LINE_MISMATCH` | Goods lines don't match | RISK_MEDIUM |

Tolerances: Amount ≤ 0.02 GEL, VAT ≤ 0.05 GEL.

---

## Safety Rules (always active)

| Rule | Enforcement |
|------|------------|
| No live RS.ge calls in `TEST_MODE=1` | `rsge_config.live_actions_enabled() → False` |
| No auto-confirm/reject/correct/cancel/activate | Feature flags = False |
| No real credentials in code or fixtures | Vault-only, fixture IDs are mock |
| No auto-post | Approval required |
| RS.ge actions are preview-only until pilot | `EXPECTED_GAP_RS_GE_LIVE_PILOT` |

---

## Gaps

| Gap Label | Description |
|-----------|-------------|
| `EXPECTED_GAP_WAYBILL_ACTION_PROTOCOL` | Waybill live actions are preview-only. Full protocol requires controlled pilot. |
| `EXPECTED_GAP_RS_GE_LIVE_PILOT` | All RS.ge live actions disabled. Controlled pilot plan in `docs/rsge_controlled_live_pilot_plan.md`. |
| `EXPECTED_GAP_CUSTOMS_DECLARATION_LINK` | Link between waybill and customs declaration not implemented. |
