# Bridge Hub BIZ-1 — GeoTrade Audit Trail & RBAC

**Task:** BIZ-1 Phase 23  
**Covers:** Audit logging, RBAC enforcement, denied action logging, security checks

---

## RBAC Roles

| Role | Can View | Can Draft | Can Approve | Can Post | RS.ge Actions |
|------|---------|-----------|-------------|----------|---------------|
| viewer | ✓ | ✗ | ✗ | ✗ | Preview only |
| accountant | ✓ | ✓ | ✗ | ✗ | Preview only |
| admin | ✓ | ✓ | ✓ | ✓ | With feature flags |
| cfo | ✓ | ✗ | ✓ | ✗ | Approval only |

Permissions enforced via:
- `app/api/policy/permission_map.py` — PERMISSION_MAP + COMPILED_PERMISSION_MAP
- `app/api/authz.py` — ROLE_PERMISSIONS dict
- `require_permission(request, "scope:action")` — raises HTTP 403 if denied

---

## Audit Log Entry Structure

```json
{
  "tenant_id": "geotrade_test",
  "user_id": "accountant-001",
  "action": "draft_created",
  "target_id": "draft-123",
  "timestamp": "2026-08-01T10:00:00Z",
  "method": "POST",
  "path": "/approval/draft",
  "status_code": 200,
  "correlation_id": "req-abc-123"
}
```

**Never in audit log:** Authorization header, access_token, pin_token, password, JWT_SECRET, DATABASE_URL, ANTHROPIC_API_KEY, BALANCE_API_KEY, VAULT_ENCRYPTION_KEY.

---

## Auditable Actions in BIZ-1 Scenario

| Action | Actor | Trigger |
|--------|-------|---------|
| `opening_balance_imported` | accountant | POST /opening-balances |
| `rsge_document_synced` | system | RS.ge sync |
| `rsge_waybill_synced` | system | Waybill sync |
| `evidence_created` | system | Document → Evidence |
| `draft_created` | accountant | Evidence → Draft |
| `draft_approved` | admin | POST /approval/approve/{id} |
| `ledger_posted` | system | Approved → Posted |
| `bank_statement_imported` | accountant | POST /bank-csv |
| `payroll_approved` | admin | POST /payroll/approve |
| `depreciation_run` | system | Monthly close |
| `period_locked` | admin/cfo | POST /accounting/periods/lock |
| `rsge_action_preview` | accountant | Preview action |
| `reversal_created` | accountant | POST /reversal |
| `period_unlock` | admin | POST /accounting/periods/unlock (audited) |

---

## RS.ge Action RBAC Matrix

| Action | Viewer | Accountant | Admin | Live Enabled? |
|--------|--------|-----------|-------|--------------|
| Preview confirm | ✗ | ✓ | ✓ | Preview only |
| Preview reject | ✗ | ✓ | ✓ | Preview only |
| Preview correct | ✗ | ✓ | ✓ | Preview only |
| Execute confirm | ✗ | ✗ | ✓ | Feature flag |
| Execute reject | ✗ | ✗ | ✓ | Feature flag |
| Execute correct | ✗ | ✗ | ✓ | Feature flag |

In `TEST_MODE=1`: All execute actions blocked regardless of role.

---

## Immutable Core Files

The following files must never be modified without engineering review:

| File | Purpose |
|------|---------|
| `app/api/engines/pattern_engine.py` | ML classification engine |
| `app/api/services/learning_service.py` | Pattern learning loop |
| `app/api/services/pattern_decay_service.py` | Pattern decay/aging |
| `app/api/transaction_classifier.py` | Top-level classifier (at `app/api/`, not `services/`) |

BIZ-1 does not touch any of these files.

---

## Tenant Isolation

Every query must include `WHERE tenant_id = $N`. GeoTrade test data uses `tenant_id = "geotrade_test"`. Cross-tenant queries raise HTTP 403 or return empty result, never cross-contaminate data.

---

## Security Checks Passed

| Check | Status |
|-------|--------|
| No real RS.ge credentials in fixtures | ✓ |
| No Authorization header in audit logs | ✓ |
| No secrets in test files | ✓ |
| RS.ge live flags = False | ✓ |
| POSTED_LEDGER_WRITES_ENABLED = false | ✓ |
| BALANCE_API_KEY not set | ✓ |
| Immutable core files untouched | ✓ |
| No production DB mutations | ✓ |
| No H71 work | ✓ |
