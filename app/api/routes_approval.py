import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List

from app.api.response_utils import error_response
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


@router.get("/queue")
def get_queue(request: Request, status: str = "", limit: int = 100, offset: int = 0):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_queue_service(status, limit, offset, tenant_id=tenant_id)


def _check_locked(result):
    """Return 409 JSONResponse if service detected a row lock conflict."""
    if isinstance(result, dict) and result.get("error", {}).get("code") == "DRAFT_LOCKED":
        return JSONResponse(status_code=409, content=result)
    return None


@router.post("/approve/{draft_id}")
@limiter.limit("30/minute")
def approve_draft(draft_id: int, request: Request):
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    log.info("action=approve draft_id=%s user=%s tenant=%s", draft_id, user_id, tenant_id)
    result = approve_draft_service(draft_id, tenant_id=tenant_id)
    return _check_locked(result) or result


@router.post("/reject/{draft_id}")
@limiter.limit("30/minute")
def reject_draft(draft_id: int, req: RejectRequest, request: Request):
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    log.info("action=reject draft_id=%s user=%s tenant=%s reason=%s", draft_id, user_id, tenant_id, req.reason)
    result = reject_draft_service(draft_id, req.reason, tenant_id=tenant_id)
    return _check_locked(result) or result


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