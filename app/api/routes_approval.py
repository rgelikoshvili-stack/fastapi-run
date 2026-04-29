import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

from app.api.response_utils import ok_response, error_response, http_error
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id
from app.api.db import get_db
import psycopg2.extras

log = logging.getLogger(__name__)
from app.api.services.approval_service import (
    get_queue_service,
    approve_draft_service,
    reject_draft_service,
    get_audit_service,
    autopilot_approve_service,
)
from app.api.services.correct_draft_service import correct_draft
from app.services.route_bridge_service import build_preview_response
from app.api.services.idempotency_service import idempotency_check, idempotency_store

router = APIRouter(prefix="/approval", tags=["approval"])


def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "limit უნდა იყოს 0 ან მეტი"},
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "offset უნდა იყოს 0 ან მეტი"},
        )


class RejectRequest(BaseModel):
    reason: Optional[str] = ""


class BatchActionRequest(BaseModel):
    action: str
    draft_ids: List[int]
    reason: Optional[str] = ""


class CorrectRequest(BaseModel):
    account_code: Optional[str] = None
    reason: Optional[str] = None
    debit_account: Optional[str] = None
    credit_account: Optional[str] = None
    user: Optional[str] = "human"


class DraftUpdateRequest(BaseModel):
    description: Optional[str] = None
    partner: Optional[str] = None
    amount: Optional[float] = None
    debit_account: Optional[str] = None
    credit_account: Optional[str] = None
    account_code: Optional[str] = None
    reason: Optional[str] = None


@router.get("/queue")
def get_queue(request: Request, status: str = "", limit: int = 100, offset: int = 0):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_queue_service(status, limit, offset, tenant_id=tenant_id)


def _check_locked(result):
    """Return 409 if service detected a row lock conflict."""
    if isinstance(result, dict) and (result.get("error") or {}).get("code") == "DRAFT_LOCKED":
        return http_error(409, result.get("message", "Draft locked"), "DRAFT_LOCKED")
    return None


@router.post("/approve/{draft_id}")
@limiter.limit("30/minute")
def approve_draft(draft_id: int, request: Request):
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    idem_key = request.headers.get("X-Idempotent-Key")
    if idem_key:
        hit = idempotency_check(tenant_id, idem_key, f"approve:{draft_id}")
        if hit is not None:
            return hit
    log.info("action=approve draft_id=%s user=%s tenant=%s", draft_id, user_id, tenant_id)
    result = approve_draft_service(draft_id, tenant_id=tenant_id)
    result = _check_locked(result) or result
    if idem_key:
        idempotency_store(tenant_id, idem_key, f"approve:{draft_id}", result)
    return result


@router.post("/reject/{draft_id}")
@limiter.limit("30/minute")
def reject_draft(draft_id: int, req: RejectRequest, request: Request):
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    idem_key = request.headers.get("X-Idempotent-Key")
    if idem_key:
        hit = idempotency_check(tenant_id, idem_key, f"reject:{draft_id}")
        if hit is not None:
            return hit
    log.info("action=reject draft_id=%s user=%s tenant=%s reason=%s", draft_id, user_id, tenant_id, req.reason)
    result = reject_draft_service(draft_id, req.reason, tenant_id=tenant_id)
    result = _check_locked(result) or result
    if idem_key:
        idempotency_store(tenant_id, idem_key, f"reject:{draft_id}", result)
    return result


@router.post("/correct/{draft_id}")
@limiter.limit("30/minute")
def correct_draft_route(draft_id: int, req: CorrectRequest, request: Request):
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    log.info("action=correct draft_id=%s user=%s tenant=%s", draft_id, user_id, tenant_id)
    payload = {
        "account_code": req.account_code,
        "reason": req.reason,
        "debit_account": req.debit_account,
        "credit_account": req.credit_account,
    }
    result = correct_draft(draft_id, payload, req.user or "human", tenant_id=tenant_id)
    return _check_locked(result) or result


@router.delete("/draft/{draft_id}")
@limiter.limit("30/minute")
def delete_draft(draft_id: int, request: Request):
    """Permanently delete a journal draft (tenant-scoped)."""
    user_id = resolve_tenant_id(getattr(request.state, "user_id", "anon") if request else "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    from app.api.db import get_db
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "DELETE FROM journal_drafts WHERE id = %s AND tenant_id = %s RETURNING id",
            (draft_id, tenant_id),
        )
        row = cur.fetchone()
        conn.commit()
        if not row:
            return http_error(404, "Draft not found", "NOT_FOUND")
        log.info("action=delete_draft draft_id=%s tenant=%s", draft_id, tenant_id)
        return ok_response("Draft deleted", {"draft_id": draft_id})
    except Exception as e:
        conn.rollback()
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()


@router.patch("/draft/{draft_id}")
def update_draft(draft_id: int, req: DraftUpdateRequest, request: Request):
    """Save draft edits without changing status (no auto-approve)."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    from app.api.db import get_db
    import psycopg2.extras, logging as _log
    _log.getLogger(__name__).info("action=update_draft draft_id=%s tenant=%s", draft_id, tenant_id)
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        fields, vals = [], []
        if req.description  is not None: fields.append("description = %s");  vals.append(req.description)
        if req.partner       is not None: fields.append("partner = %s");       vals.append(req.partner)
        if req.amount        is not None: fields.append("amount = %s");        vals.append(req.amount)
        if req.debit_account is not None: fields.append("debit_account = %s"); vals.append(req.debit_account)
        if req.credit_account is not None: fields.append("credit_account = %s"); vals.append(req.credit_account)
        if req.account_code  is not None: fields.append("account_code = %s"); vals.append(req.account_code)
        if req.reason        is not None: fields.append("reason = %s");        vals.append(req.reason)
        if not fields:
            return {"ok": True, "message": "no_changes"}
        fields.append("updated_at = NOW()")
        vals += [draft_id, tenant_id]
        cur.execute(
            f"UPDATE journal_drafts SET {', '.join(fields)} WHERE id = %s AND tenant_id = %s",
            vals,
        )
        conn.commit()
        return {"ok": True, "draft_id": draft_id}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()


@router.get("/audit")
def get_audit_log(request: Request, limit: int = 50, offset: int = 0):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_audit_service(limit, offset, tenant_id=tenant_id)


@router.post("/autopilot")
def run_autopilot(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return autopilot_approve_service(tenant_id=tenant_id)


@router.post("/preview")
def preview_draft(payload: dict, request: Request):
    """Unified preview: uses posting_preview_service when draft_id is supplied (full Dr/Cr impact),
    otherwise falls back to simple summary preview."""
    try:
        draft_id = payload.get("draft_id") or payload.get("id")
        if draft_id:
            tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
            from app.api.services.posting_preview_service import preview_posting_service
            return preview_posting_service(draft_id=int(draft_id), tenant_id=tenant_id)
        return build_preview_response(payload)
    except Exception as e:
        return error_response("Preview failed", "PREVIEW_ERROR", str(e))


@router.get("/stats")
def get_stats(request: Request):
    """Real-time approval queue statistics."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('pending', 'pending_human_review')) AS pending_count,
                    COUNT(*) FILTER (WHERE status = 'auto_approved') AS auto_approved,
                    COUNT(*) FILTER (WHERE status = 'approved') AS manual_approved,
                    COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
                    COALESCE(AVG(CAST(confidence AS FLOAT)), 0) AS avg_confidence
                FROM journal_drafts
                WHERE tenant_id::text = %s
            """, (tenant_id,))
            row = dict(cur.fetchone())
        finally:
            cur.close()
            conn.close()
        return {
            "ok": True,
            "pending_count": int(row["pending_count"] or 0),
            "auto_approved": int(row["auto_approved"] or 0),
            "manual_approved": int(row["manual_approved"] or 0),
            "rejected": int(row["rejected"] or 0),
            "confidence": round(float(row["avg_confidence"] or 0), 4),
            "tenant_id": tenant_id,
        }
    except Exception as e:
        log.error("get_stats error: %s", e)
        return error_response("Stats failed", "STATS_ERROR", str(e))


@router.post("/reclassify")
def reclassify_unclassified(request: Request):
    """Re-run classification on drafts with NULL debit_account/credit_account."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        from app.knowledge.journal_builder import classify_transaction
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """SELECT id, description, amount FROM journal_drafts
               WHERE tenant_id = %s AND (debit_account IS NULL OR credit_account IS NULL
                                        OR debit_account = '????' OR credit_account = '????')
               ORDER BY id LIMIT 200""",
            (tenant_id,),
        )
        drafts = [dict(r) for r in cur.fetchall()]
        updated = 0
        for d in drafts:
            try:
                res = classify_transaction(d["description"] or "", tenant_id)
                acc = res.get("account", "")
                if not acc:
                    continue
                # determine debit/credit from account range
                a = int(acc) if acc.isdigit() else 0
                if 1000 <= a <= 1999:
                    dr, cr = acc, "3110"
                elif 2000 <= a <= 2999:
                    dr, cr = acc, "3110"
                elif 3000 <= a <= 3999:
                    dr, cr = "1210", acc
                elif 5000 <= a <= 5999:
                    dr, cr = acc, "3110"
                elif 7000 <= a <= 7999:
                    dr, cr = acc, "1210"
                else:
                    dr, cr = acc, "3110"
                cur.execute(
                    """UPDATE journal_drafts SET debit_account=%s, credit_account=%s, account_code=%s
                       WHERE id=%s AND tenant_id=%s""",
                    (dr, cr, acc, d["id"], tenant_id),
                )
                updated += 1
            except Exception:
                pass
        conn.commit()
        cur.close()
        conn.close()
        return {"ok": True, "reclassified": updated, "total_unclassified": len(drafts)}
    except Exception as e:
        return error_response("Reclassify failed", "RECLASSIFY_ERROR", str(e))


@router.post("/batch-action")
@limiter.limit("30/minute")
def batch_action(body: BatchActionRequest, request: Request):
    """Execute approve/reject/correct on multiple drafts at once."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.draft_ids:
        return error_response("No drafts selected", "BATCH_ERROR", "draft_ids is empty")
    valid_actions = {"approve", "reject", "correct"}
    if body.action not in valid_actions:
        return error_response("Invalid action", "BATCH_ERROR", f"action must be one of {valid_actions}")

    status_map = {"approve": "approved", "reject": "rejected", "correct": "needs_correction"}
    new_status = status_map[body.action]

    try:
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute("""
                UPDATE journal_drafts
                SET status = %s, updated_at = NOW()
                WHERE id = ANY(%s)
                  AND tenant_id::text = %s
                  AND status NOT IN ('approved', 'rejected', 'posted')
            """, (new_status, body.draft_ids, tenant_id))
            affected = cur.rowcount
            conn.commit()
        finally:
            cur.close()
            conn.close()
        log.info("batch_action action=%s affected=%s tenant=%s", body.action, affected, tenant_id)
        return {"ok": True, "action": body.action, "affected": affected, "tenant_id": tenant_id}
    except Exception as e:
        log.error("batch_action error: %s", e)
        return error_response("Batch action failed", "BATCH_ERROR", str(e))


# ── CFO Second Approval ───────────────────────────────────────────────────────

@router.post("/cfo-approve/{draft_id}")
def cfo_approve(draft_id: int, request: Request):
    """CFO second-level approval for high-value drafts (≥ ₾10,000)."""
    from app.api.authz import require_permission
    require_permission(request, "approval:cfo")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    user = getattr(request.state, "user_email", "cfo")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT * FROM journal_drafts
            WHERE id = %s AND tenant_id = %s AND status = 'awaiting_cfo'
            FOR UPDATE NOWAIT
        """, (draft_id, tenant_id))
        draft = cur.fetchone()
        if not draft:
            return http_error(404, "Draft not found or not awaiting CFO approval", "NOT_FOUND")

        cur.execute("""
            UPDATE journal_drafts
            SET status = 'approved',
                approved_by_mode = 'dual_human',
                updated_at = NOW()
            WHERE id = %s AND tenant_id = %s
            RETURNING id, status, amount
        """, (draft_id, tenant_id))
        updated = cur.fetchone()
        conn.commit()
        log.info("action=cfo_approve draft=%s tenant=%s by=%s", draft_id, tenant_id, user)
        return {"ok": True, "id": draft_id, "status": "approved", "approved_by": user, "level": "CFO"}
    except Exception as e:
        conn.rollback()
        return http_error(500, str(e), "CFO_APPROVE_ERROR")
    finally:
        cur.close()
        conn.close()


@router.get("/awaiting-cfo")
def list_awaiting_cfo(request: Request):
    """List all drafts awaiting CFO second approval."""
    from app.api.authz import require_permission
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, date, description, partner, amount, currency, status, created_at
            FROM journal_drafts
            WHERE tenant_id = %s AND status = 'awaiting_cfo'
            ORDER BY amount DESC
        """, (tenant_id,))
        rows = [dict(r) for r in cur.fetchall()]
        for r in rows:
            r["date"] = str(r["date"])[:10] if r.get("date") else None
            r["created_at"] = str(r["created_at"])[:19] if r.get("created_at") else None
            r["amount"] = float(r["amount"] or 0)
    finally:
        cur.close()
        conn.close()

    return {"ok": True, "data": {"items": rows, "count": len(rows)}}
