# RS.ge — Action Safety Model

## Principle

Every RS.ge state-changing action (confirm, reject, correct, cancel, activate) follows a strict two-phase approach: **Preview → Execute**. No action is executed without explicit human approval.

---

## 13 Required Gates (All Must Pass)

Before any live RS.ge action executes:

1. `RSGE_ENABLED=true`
2. `RSGE_TEST_MODE=true` (for test actions) or explicit live override
3. `RSGE_LIVE_ACTIONS_ENABLED=true` (for production — currently always false)
4. Action-specific flag: `RSGE_ALLOW_TEST_{ACTION}=true`
5. Authenticated Bridge Hub user (valid JWT)
6. User has RBAC role: `accountant` or `admin`
7. `require_permission(request, "posting:write")` passes
8. Preview generated for this doc_id + action
9. `approved_by` field set (approver user_id)
10. RS.ge connector in live mode (not demo)
11. Document exists in local DB (rsge_documents or rsge_waybills)
12. Audit log entry written BEFORE action
13. Audit log entry finalized AFTER action

If any gate fails → HTTP 403 or 400 response, no RS.ge call made.

---

## Feature Flags (rsge_config.py)

```python
RSGE_ENABLED              # Global enable
RSGE_READ_ONLY            # Block all mutations (default: true)
RSGE_TEST_MODE            # Enable test-mode actions
RSGE_LIVE_ACTIONS_ENABLED # Allow production RS.ge mutations (default: false)
RSGE_DRY_RUN              # Dry-run mode
RSGE_ALLOW_TEST_CONFIRM   # Specific test flag
RSGE_ALLOW_TEST_REJECT
RSGE_ALLOW_TEST_CORRECT
RSGE_ALLOW_TEST_CANCEL
RSGE_ALLOW_TEST_ACTIVATE
```

`require_test_mode(action)` raises `HTTPException(403)` if not in test mode.
`require_action_flag(action)` raises `HTTPException(403)` if specific flag not set.

---

## Two-Phase Action Protocol

### Phase 1: Preview
```
POST /rs-ge/documents/{id}/preview-confirm
```
Returns:
```json
{
  "valid": true,
  "action": "confirm",
  "test_mode": true,
  "requires_approval": true,
  "payload_preview": {"su": "****", "sp": "****", "rsge_id": "100"},
  "accounting_impact": {"impact": "positive", "amount": 1180.0},
  "warnings": [],
  "current_status": "0"
}
```
- No RS.ge call made
- Credentials redacted
- Shows accounting impact

### Phase 2: Execute (Test Mode)
```
POST /rs-ge/documents/{id}/test-confirm
{"approved_by": "user_id_456"}
```
Steps:
1. `require_action_flag("confirm")` — blocks if not test mode
2. Load document from rsge_documents
3. Write audit record (status="executing")
4. `_dispatch_action(connector, "confirm", rsge_id, "document")`
5. Update document status in DB
6. Write status history
7. Finalize audit record

---

## Audit Log (rsge_actions table)

Every action writes two records:

**Before:**
```
action_status = "executing"
preview_payload = redacted JSON
requested_by = bridge_hub_user_id
approved_by = approver_id
is_test_mode = TRUE
```

**After:**
```
action_status = "completed" | "failed"
response_status = "ok" | "error"
response_raw = {success, status} (no credentials)
error_text = if failed
completed_at = NOW()
```

---

## What is Permanently Blocked

- Production mutations without RSGE_LIVE_ACTIONS_ENABLED=true
- Auto-confirm / auto-reject / auto-activate (no batch actions)
- Auto-posting of accounting entries from RS.ge actions
- Balance.ge activation
- POSTED_LEDGER_WRITES_ENABLED change
- H71 related work
- Credentials in API responses or logs
- Token in frontend

---

## Connector Demo Mode Safety

When `connector.mode == "demo"`:
```python
return {"success": True, "status": f"demo_{method_name}", "erp_id": doc_id}
```
No HTTP call to RS.ge is made. Safe for testing.
