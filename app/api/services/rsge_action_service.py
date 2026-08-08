"""app/api/services/rsge_action_service.py — RS.ge test-mode action execution.

Valid actions: confirm | reject | correct | cancel | activate

Every action has two phases:
  1. preview_action() — generate a human-readable preview (no RS.ge call)
  2. execute_test_action() — call RS.ge test endpoint, audit-log before+after

Invariants:
  - execute_test_action() calls rsge_config.require_action_flag() — blocks if not test mode.
  - Raw credentials are NEVER in the audit log.
  - Auto-action (without user selection) is NEVER allowed.
  - Approval reference (approved_by) is required for execute.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from app.api.services.rsge_config import require_action_flag

log = logging.getLogger(__name__)

_INVOICE_ACTIONS = frozenset({"confirm", "reject", "correct", "cancel"})
_WAYBILL_ACTIONS = frozenset({"activate", "cancel"})
_ALL_ACTIONS = _INVOICE_ACTIONS | _WAYBILL_ACTIONS


# ── Preview ───────────────────────────────────────────────────────────────────

async def preview_action(
    conn,
    tenant_id: str,
    local_doc_id: int,
    action: str,
    doc_type: str = "document",
) -> dict:
    """Generate an action preview — no RS.ge call, no state change."""
    if action not in _ALL_ACTIONS:
        return {"valid": False, "error": f"Unknown action: {action}. Valid: {sorted(_ALL_ACTIONS)}"}

    table = "rsge_documents" if doc_type == "document" else "rsge_waybills"
    from app.api.db import _q
    row = await conn.fetchrow(
        _q(f"SELECT * FROM {table} WHERE id = %s AND tenant_id = %s"),
        local_doc_id, tenant_id,
    )
    if not row:
        return {"valid": False, "error": f"{table} id={local_doc_id} not found"}

    doc = dict(row)
    current_status = doc.get("rsge_status") or doc.get("rsge_status_code") or "unknown"
    amount = float(doc.get("amount") or doc.get("full_amount") or 0)

    warnings = _action_warnings(action, current_status, amount)
    accounting_impact = _accounting_impact(action, doc)

    return {
        "valid": True,
        "action": action,
        "doc_type": doc_type,
        "local_id": local_doc_id,
        "rsge_id": doc.get("rsge_id"),
        "current_status": current_status,
        "current_amount": amount,
        "requested_action": action,
        "payload_preview": _redacted_payload(action, doc),
        "accounting_impact": accounting_impact,
        "warnings": warnings,
        "test_mode": True,
        "requires_approval": True,
        "note": "This is a TEST MODE action. No production RS.ge will be affected.",
    }


def _action_warnings(action: str, current_status: str, amount: float) -> list:
    warnings = []
    if action == "confirm" and current_status not in ("0", "saved", ""):
        warnings.append(f"Document status is '{current_status}' — confirm may be rejected by RS.ge")
    if action == "cancel" and current_status in ("2", "confirmed", "completed"):
        warnings.append("Cancelling a confirmed document may not be reversible")
    if action == "correct" and amount == 0:
        warnings.append("Amount is zero — correction may create a zero-value document")
    return warnings


def _accounting_impact(action: str, doc: dict) -> dict:
    amount = float(doc.get("amount") or doc.get("full_amount") or 0)
    direction = doc.get("direction") or "unknown"
    if action in ("confirm", "activate"):
        return {"impact": "positive", "direction": direction, "amount": amount,
                "note": "Confirms liability/receivable in ledger"}
    if action in ("cancel", "reject"):
        return {"impact": "reversal", "direction": direction, "amount": -amount,
                "note": "Cancels outstanding liability/receivable"}
    if action == "correct":
        return {"impact": "correction", "direction": direction, "amount": amount,
                "note": "Creates correction document — review new amounts"}
    return {}


def _redacted_payload(action: str, doc: dict) -> dict:
    """Return action payload with sensitive fields redacted."""
    return {
        "action": action,
        "rsge_id": doc.get("rsge_id"),
        "reg_no": doc.get("reg_no") or doc.get("waybill_number"),
        "amount": float(doc.get("amount") or doc.get("full_amount") or 0),
        "su": "****",   # always redacted
        "sp": "****",   # always redacted
        "note": "[credentials redacted from preview]",
    }


# ── Execute ───────────────────────────────────────────────────────────────────

async def execute_test_action(
    conn,
    tenant_id: str,
    local_doc_id: int,
    action: str,
    requested_by: str,
    approved_by: str,
    connector,
    doc_type: str = "document",
    comment: str = "",
) -> dict:
    """Execute a test-mode RS.ge action.

    Calls require_action_flag() → blocks if not test mode.
    Writes audit log before AND after.
    Returns action result (never contains raw credentials or token).
    """
    if not approved_by:
        raise ValueError("approved_by is required for RS.ge test actions")

    require_action_flag(action)

    table = "rsge_documents" if doc_type == "document" else "rsge_waybills"
    from app.api.db import _q
    row = await conn.fetchrow(
        _q(f"SELECT * FROM {table} WHERE id = %s AND tenant_id = %s"),
        local_doc_id, tenant_id,
    )
    if not row:
        return {"success": False, "error": f"{table} id={local_doc_id} not found"}

    doc = dict(row)
    rsge_id = doc.get("rsge_id") or ""

    # Write audit BEFORE action
    action_id = await _write_audit(
        conn, tenant_id, local_doc_id, doc_type, action,
        requested_by, approved_by, "executing", doc,
    )

    result = await _dispatch_action(connector, action, rsge_id, doc_type, comment)

    new_status = result.get("status") or result.get("rsge_status") or ""
    success = result.get("success", False)

    # Update document status if changed
    if new_status and success:
        await _update_doc_status(conn, tenant_id, local_doc_id, table, new_status)

    # Write status history
    await _write_status_history(
        conn, tenant_id, local_doc_id, doc_type,
        doc.get("rsge_status") or doc.get("rsge_status_code") or "",
        new_status, requested_by, action,
    )

    # Update audit record AFTER
    await _finalize_audit(conn, action_id, success, result)

    return {
        "success": success,
        "action": action,
        "rsge_id": rsge_id,
        "action_id": action_id,
        "new_status": new_status,
        "test_mode": True,
        "error": result.get("error") if not success else None,
    }


async def _dispatch_action(
    connector, action: str, rsge_id: str, doc_type: str, comment: str,
) -> dict:
    """Call the appropriate connector method for the action."""
    try:
        int_id = int(rsge_id) if rsge_id.isdigit() else 0
        if doc_type == "document":
            if action == "confirm":
                return _soap_invoice_action(connector, "confirm_invoice", int_id)
            if action == "reject":
                return _soap_invoice_action(connector, "reject_invoice", int_id,
                                            extra={"comment": comment or "RS.ge reject"})
            if action == "correct":
                return _soap_invoice_action(connector, "correct_invoice", int_id)
            if action == "cancel":
                return _soap_invoice_action(connector, "cancel_invoice", int_id)
        else:  # waybill
            if action == "activate":
                r = connector.get_waybill(int_id)
                # activate by saving with status=1
                if "error" not in r:
                    draft = dict(r)
                    draft["status"] = 1
                    return connector.post(draft)
            if action == "cancel":
                return connector.cancel_waybill(int_id)
    except Exception as exc:
        log.warning("[RS.GE] dispatch_action failed: %s", exc)
        return {"success": False, "error": str(exc)[:200]}
    return {"success": False, "error": f"Unknown action/doc_type: {action}/{doc_type}"}


def _soap_invoice_action(connector, method_name: str, doc_id: int, extra: dict = None) -> dict:
    """Call a named method on the invoice connector (if available in test mode)."""
    if connector.mode == "demo":
        return {"success": True, "status": f"demo_{method_name}", "erp_id": doc_id}
    try:
        from app.api.connectors.rs_ge_connector import _soap_call, _INVOICE_WSDL, _INV_NS, _xml_text
        params = {"su": connector.su, "sp": connector.sp, "invois_id": doc_id}
        if extra:
            params.update(extra)
        resp = _soap_call(_INVOICE_WSDL, method_name, _INV_NS, params)
        ok_el = resp.find(f"{method_name}Result")
        ok = ok_el is not None and (ok_el.text or "").lower() == "true"
        return {"success": ok, "status": "confirmed" if ok else "failed",
                "erp_id": doc_id}
    except Exception as exc:
        return {"success": False, "error": str(exc)[:200]}


# ── Audit helpers ─────────────────────────────────────────────────────────────

async def _write_audit(
    conn, tenant_id: str, local_doc_id: int, doc_type: str,
    action: str, requested_by: str, approved_by: str,
    status: str, doc: dict,
) -> int:
    try:
        from app.api.db import _q
        row = await conn.fetchrow(
            _q("""
                INSERT INTO rsge_actions
                  (tenant_id, rsge_doc_id, action, doc_type, is_test_mode, is_dry_run,
                   requested_by, approved_by, action_status, preview_payload, created_at)
                VALUES (%s, %s, %s, %s, TRUE, FALSE, %s, %s, %s, %s, NOW())
                RETURNING id
            """),
            tenant_id,
            local_doc_id if doc_type == "document" else None,
            action, doc_type, requested_by, approved_by, status,
            json.dumps(_redacted_payload(action, doc)),
        )
        return row["id"] if row else 0
    except Exception as exc:
        log.debug("_write_audit failed: %s", exc)
        return 0


async def _finalize_audit(conn, action_id: int, success: bool, result: dict) -> None:
    if not action_id:
        return
    try:
        from app.api.db import _q
        await conn.execute(
            _q("""
                UPDATE rsge_actions
                SET action_status = %s,
                    response_status = %s,
                    response_raw = %s,
                    error_text = %s,
                    completed_at = NOW()
                WHERE id = %s
            """),
            "completed" if success else "failed",
            "ok" if success else "error",
            json.dumps({k: v for k, v in result.items() if k not in ("su", "sp", "token")}),
            result.get("error"),
            action_id,
        )
    except Exception as exc:
        log.debug("_finalize_audit failed: %s", exc)


async def _update_doc_status(conn, tenant_id: str, local_id: int, table: str, new_status: str):
    try:
        from app.api.db import _q
        await conn.execute(
            _q(f"UPDATE {table} SET rsge_status = %s WHERE id = %s AND tenant_id = %s"),
            new_status, local_id, tenant_id,
        )
    except Exception as exc:
        log.debug("_update_doc_status skipped: %s", exc)


async def _write_status_history(conn, tenant_id, local_id, doc_type, old_s, new_s, actor, action):
    try:
        from app.api.db import _q
        doc_id_col = "rsge_doc_id" if doc_type == "document" else "rsge_doc_id"
        await conn.execute(
            _q("""
                INSERT INTO rsge_document_status_history
                  (rsge_doc_id, tenant_id, old_status, new_status, changed_by, note)
                VALUES (%s, %s, %s, %s, %s, %s)
            """),
            local_id, tenant_id, old_s, new_s, actor, f"action={action}",
        )
    except Exception as exc:
        log.debug("_write_status_history skipped: %s", exc)
