import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List

from app.api.response_utils import ok_response, error_response, http_error
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.db import get_conn, _q
from app.api.services.cache_service import cache_get, cache_set, cache_clear_prefix, CACHE_TTL

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
            detail={"error": "INVALID_PAGINATION", "message": "limit áƒ£áƒœáƒ“áƒ áƒ˜áƒ§áƒáƒ¡ 0 áƒáƒœ áƒ›áƒ”áƒ¢áƒ˜"},
        )
    if offset < 0:
        raise HTTPException(
            status_code=422,
            detail={"error": "INVALID_PAGINATION", "message": "offset áƒ£áƒœáƒ“áƒ áƒ˜áƒ§áƒáƒ¡ 0 áƒáƒœ áƒ›áƒ”áƒ¢áƒ˜"},
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


@router.get("/suggestions")
async def get_suggestions(request: Request, q: str = "", field: str = "partner"):
    """Return autocomplete suggestions for partner/description fields from historical drafts."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if len(q) < 2:
        return ok_response("Suggestions", [])
    allowed_fields = {"partner", "description"}
    if field not in allowed_fields:
        return ok_response("Suggestions", [])

    col = "partner" if field == "partner" else "description"
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q(f"""
                SELECT {col} AS val, COUNT(*) AS cnt
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND {col} ILIKE %s
                  AND {col} IS NOT NULL
                  AND {col} != ''
                GROUP BY {col}
                ORDER BY cnt DESC
                LIMIT 8
            """), tenant_id, f"%{q}%")
        return ok_response("Suggestions", [{"value": r["val"], "count": r["cnt"]} for r in rows])
    except Exception as e:
        log.error("get_suggestions error: %s", e)
        return ok_response("Suggestions", [])


@router.get("/queue")
async def get_queue(request: Request, status: str = "", limit: int = 100, offset: int = 0, q: str = ""):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_queue_service(status, limit, offset, tenant_id=tenant_id, q=q)


def _check_locked(result):
    """Return 409 if service detected a row lock conflict."""
    if isinstance(result, dict) and (result.get("error") or {}).get("code") == "DRAFT_LOCKED":
        return http_error(409, result.get("message", "Draft locked"), "DRAFT_LOCKED")
    return None


@router.post("/approve/{draft_id}")
@limiter.limit("30/minute")
async def approve_draft(draft_id: int, request: Request):
    require_permission(request, "approval:write")
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    idem_key = request.headers.get("X-Idempotent-Key")
    if idem_key:
        hit = idempotency_check(tenant_id, idem_key, f"approve:{draft_id}")
        if hit is not None:
            return hit
    log.info("action=approve draft_id=%s user=%s tenant=%s", draft_id, user_id, tenant_id)
    result = await approve_draft_service(draft_id, tenant_id=tenant_id)
    result = _check_locked(result) or result
    if idem_key:
        idempotency_store(tenant_id, idem_key, f"approve:{draft_id}", result)
    cache_clear_prefix(f"approval_stats:{tenant_id}")
    cache_clear_prefix(f"dashboard_live:{tenant_id}")
    return result


@router.post("/reject/{draft_id}")
@limiter.limit("30/minute")
async def reject_draft(draft_id: int, req: RejectRequest, request: Request):
    require_permission(request, "approval:write")
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    idem_key = request.headers.get("X-Idempotent-Key")
    if idem_key:
        hit = idempotency_check(tenant_id, idem_key, f"reject:{draft_id}")
        if hit is not None:
            return hit
    log.info("action=reject draft_id=%s user=%s tenant=%s reason=%s", draft_id, user_id, tenant_id, req.reason)
    result = await reject_draft_service(draft_id, req.reason, tenant_id=tenant_id)
    result = _check_locked(result) or result
    if idem_key:
        idempotency_store(tenant_id, idem_key, f"reject:{draft_id}", result)
    cache_clear_prefix(f"approval_stats:{tenant_id}")
    cache_clear_prefix(f"dashboard_live:{tenant_id}")
    return result


@router.post("/correct/{draft_id}")
@limiter.limit("30/minute")
async def correct_draft_route(draft_id: int, req: CorrectRequest, request: Request):
    require_permission(request, "approval:write")
    user_id = getattr(request.state, "user_id", "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    log.info("action=correct draft_id=%s user=%s tenant=%s", draft_id, user_id, tenant_id)
    payload = {
        "account_code": req.account_code,
        "reason": req.reason,
        "debit_account": req.debit_account,
        "credit_account": req.credit_account,
    }
    result = await correct_draft(draft_id, payload, req.user or "human", tenant_id=tenant_id)
    return _check_locked(result) or result


@router.delete("/draft/{draft_id}")
@limiter.limit("30/minute")
async def delete_draft(draft_id: int, request: Request):
    """Permanently delete a journal draft (tenant-scoped)."""
    require_permission(request, "approval:write")
    user_id = resolve_tenant_id(getattr(request.state, "user_id", "anon") if request else "anon")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                _q("DELETE FROM journal_drafts WHERE id = %s AND tenant_id = %s RETURNING id"),
                draft_id, tenant_id,
            )
        if not row:
            return http_error(404, "Draft not found", "NOT_FOUND")
        log.info("action=delete_draft draft_id=%s tenant=%s", draft_id, tenant_id)
        return ok_response("Draft deleted", {"draft_id": draft_id})
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))


@router.patch("/draft/{draft_id}")
async def update_draft(draft_id: int, req: DraftUpdateRequest, request: Request):
    """Save draft edits without changing status (no auto-approve)."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    log.info("action=update_draft draft_id=%s tenant=%s", draft_id, tenant_id)

    fields, vals = [], []
    if req.description   is not None: fields.append("description = %s");   vals.append(req.description)
    if req.partner        is not None: fields.append("partner = %s");        vals.append(req.partner)
    if req.amount         is not None: fields.append("amount = %s");         vals.append(req.amount)
    if req.debit_account  is not None: fields.append("debit_account = %s");  vals.append(req.debit_account)
    if req.credit_account is not None: fields.append("credit_account = %s"); vals.append(req.credit_account)
    if req.account_code   is not None: fields.append("account_code = %s");   vals.append(req.account_code)
    if req.reason         is not None: fields.append("reason = %s");         vals.append(req.reason)
    if not fields:
        return ok_response("No changes requested", {"draft_id": draft_id})
    fields.append("updated_at = NOW()")
    vals += [draft_id, tenant_id]
    try:
        async with get_conn() as conn:
            await conn.execute(
                _q(f"UPDATE journal_drafts SET {', '.join(fields)} WHERE id = %s AND tenant_id = %s"),
                *vals,
            )
        return ok_response("Draft updated", {"draft_id": draft_id})
    except Exception as e:
        return error_response("Draft update failed", "UPDATE_ERROR", str(e))


@router.get("/audit")
async def get_audit_log(request: Request, limit: int = 50, offset: int = 0):
    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_audit_service(limit, offset, tenant_id=tenant_id)


@router.post("/autopilot")
def run_autopilot(request: Request):
    require_permission(request, "approval:write")
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
async def get_stats(request: Request):
    """Real-time approval queue statistics."""
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    cache_key = f"approval_stats:{tenant_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("""
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('pending', 'pending_human_review')) AS pending_count,
                    COUNT(*) FILTER (WHERE status = 'auto_approved') AS auto_approved,
                    COUNT(*) FILTER (WHERE status = 'approved') AS manual_approved,
                    COUNT(*) FILTER (WHERE status = 'rejected') AS rejected,
                    COALESCE(AVG(CAST(confidence AS FLOAT)), 0) AS avg_confidence
                FROM journal_drafts
                WHERE tenant_id = %s
            """), tenant_id)
        result = {
            "ok": True,
            "pending_count": int(row["pending_count"] or 0),
            "auto_approved": int(row["auto_approved"] or 0),
            "manual_approved": int(row["manual_approved"] or 0),
            "rejected": int(row["rejected"] or 0),
            "confidence": round(float(row["avg_confidence"] or 0), 4),
            "tenant_id": tenant_id,
        }
        cache_set(cache_key, result, CACHE_TTL["approval_stats"])
        return result
    except Exception as e:
        log.error("get_stats error: %s", e)
        return error_response("Stats failed", "STATS_ERROR", str(e))


@router.post("/reclassify")
async def reclassify_unclassified(request: Request):
    """Re-run classification on drafts with NULL debit_account/credit_account."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        from app.knowledge.journal_builder import classify_transaction
        async with get_conn() as conn:
            drafts = [dict(r) for r in await conn.fetch(_q(
                """SELECT id, description, amount FROM journal_drafts
                   WHERE tenant_id = %s AND (debit_account IS NULL OR credit_account IS NULL
                                            OR debit_account = '????' OR credit_account = '????')
                   ORDER BY id LIMIT 200"""),
                tenant_id)]
            updated = 0
            for d in drafts:
                try:
                    res = classify_transaction(d["description"] or "", tenant_id)
                    acc = res.get("account", "")
                    if not acc:
                        continue
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
                    await conn.execute(_q(
                        """UPDATE journal_drafts SET debit_account=%s, credit_account=%s, account_code=%s
                           WHERE id=%s AND tenant_id=%s"""),
                        dr, cr, acc, d["id"], tenant_id)
                    updated += 1
                except Exception:
                    pass
        return ok_response("Reclassification complete", {"reclassified": updated, "total_unclassified": len(drafts)})
    except Exception as e:
        return error_response("Reclassify failed", "RECLASSIFY_ERROR", str(e))


@router.post("/batch-action")
@limiter.limit("30/minute")
async def batch_action(body: BatchActionRequest, request: Request):
    """Execute approve/reject/correct on multiple drafts at once."""
    require_permission(request, "approval:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not body.draft_ids:
        return error_response("No drafts selected", "BATCH_ERROR", "draft_ids is empty")
    valid_actions = {"approve", "reject", "correct"}
    if body.action not in valid_actions:
        return error_response("Invalid action", "BATCH_ERROR", f"action must be one of {valid_actions}")

    status_map = {"approve": "approved", "reject": "rejected", "correct": "needs_correction"}
    new_status = status_map[body.action]

    try:
        async with get_conn() as conn:
            st = await conn.execute(_q("""
                UPDATE journal_drafts
                SET status = %s, updated_at = NOW()
                WHERE id = ANY(%s)
                  AND tenant_id = %s
                  AND status NOT IN ('approved', 'rejected', 'posted')
            """), new_status, body.draft_ids, tenant_id)
            affected = int(st.split()[-1])
        log.info("batch_action action=%s affected=%s tenant=%s", body.action, affected, tenant_id)
        return ok_response("Batch action complete", {"action": body.action, "affected": affected, "tenant_id": tenant_id})
    except Exception as e:
        log.error("batch_action error: %s", e)
        return error_response("Batch action failed", "BATCH_ERROR", str(e))


# â”€â”€ Draft Attachment â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/draft/{draft_id}/attach")
async def attach_file_to_draft(draft_id: int, request: Request, file=None):
    """Attach a file to an existing journal draft."""
    require_permission(request, "approval:write")
    from app.api.services.storage_service import upload_file as gcs_upload, generate_signed_url
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    form = await request.form()
    file = form.get("file")
    if not file:
        return error_response("No file provided", "ATTACH_ERROR", "file field missing")

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        return error_response("File too large (max 20MB)", "ATTACH_ERROR", "size exceeds 20MB")

    allowed_exts = ('.pdf', '.png', '.jpg', '.jpeg', '.xlsx', '.xls', '.csv')
    fname = (file.filename or "file").lower()
    if not any(fname.endswith(ext) for ext in allowed_exts):
        return error_response("File type not allowed", "ATTACH_ERROR", f"allowed: {allowed_exts}")

    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT id FROM journal_drafts WHERE id = %s AND tenant_id = %s"),
                draft_id, tenant_id)
            if not row:
                return http_error(404, "Draft not found", "NOT_FOUND")

            gcs_path = gcs_upload(file_bytes, file.filename, file.content_type or "application/octet-stream", tenant_id)

            await conn.execute(_q(
                """UPDATE journal_drafts
                   SET attached_file_path = %s, attached_file_name = %s, attached_file_size = %s
                   WHERE id = %s AND tenant_id = %s"""),
                gcs_path, file.filename, len(file_bytes), draft_id, tenant_id)
        log.info("action=draft_attach draft_id=%s tenant=%s file=%s", draft_id, tenant_id, file.filename)
        return ok_response("Draft attachment saved", {"draft_id": draft_id, "file_name": file.filename, "file_size": len(file_bytes)})
    except Exception as e:
        log.error("attach_file_to_draft draft_id=%s: %s", draft_id, e)
        return error_response("Attach failed", "ATTACH_ERROR", str(e))


@router.get("/draft/{draft_id}/attachment")
async def get_draft_attachment(draft_id: int, request: Request):
    """Return signed URL or file info for a draft's attachment."""
    from app.api.services.storage_service import generate_signed_url, download_file
    from fastapi.responses import Response
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT attached_file_path, attached_file_name, attached_file_size FROM journal_drafts "
            "WHERE id = %s AND tenant_id = %s"),
            draft_id, tenant_id)

    if not row or not row["attached_file_name"]:
        return http_error(404, "No attachment found", "NOT_FOUND")

    gcs_path = row["attached_file_path"]
    file_name = row["attached_file_name"]
    file_size = row["attached_file_size"]

    if gcs_path:
        signed_url = generate_signed_url(gcs_path, expires_in=900)
        if signed_url:
            return ok_response("Draft attachment URL", {"signed_url": signed_url, "file_name": file_name, "file_size": file_size})
        try:
            content = download_file(gcs_path)
            return Response(content=content, media_type="application/octet-stream",
                            headers={"Content-Disposition": f'inline; filename="{file_name}"'})
        except Exception as e:
            log.error("get_draft_attachment gcs_download failed: %s", e)

    return http_error(404, "Attachment file unavailable", "NOT_FOUND")


@router.delete("/draft/{draft_id}/attachment")
async def delete_draft_attachment(draft_id: int, request: Request):
    """Remove attachment from a draft."""
    require_permission(request, "approval:write")
    from app.api.services.storage_service import delete_file
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT attached_file_path FROM journal_drafts WHERE id = %s AND tenant_id = %s"),
                draft_id, tenant_id)
            if not row:
                return http_error(404, "Draft not found", "NOT_FOUND")

            if row["attached_file_path"]:
                delete_file(row["attached_file_path"])

            await conn.execute(_q(
                "UPDATE journal_drafts SET attached_file_path=NULL, attached_file_name=NULL, attached_file_size=NULL "
                "WHERE id=%s AND tenant_id=%s"),
                draft_id, tenant_id)
        return ok_response("Draft attachment deleted", {"draft_id": draft_id, "removed": True})
    except Exception as e:
        return error_response("Delete failed", "ATTACH_ERROR", str(e))


# â”€â”€ CFO Second Approval â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/cfo-approve/{draft_id}")
async def cfo_approve(draft_id: int, request: Request):
    """CFO second-level approval for high-value drafts (â‰¥ â‚¾10,000)."""
    require_permission(request, "approval:cfo")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    user = getattr(request.state, "user_email", "cfo")

    try:
        async with get_conn() as conn:
            async with conn.transaction():
                draft = await conn.fetchrow(_q("""
                    SELECT * FROM journal_drafts
                    WHERE id = %s AND tenant_id = %s AND status = 'awaiting_cfo'
                    FOR UPDATE NOWAIT
                """), draft_id, tenant_id)
                if not draft:
                    return http_error(404, "Draft not found or not awaiting CFO approval", "NOT_FOUND")

                await conn.execute(_q("""
                    UPDATE journal_drafts
                    SET status = 'approved',
                        approved_by_mode = 'dual_human',
                        updated_at = NOW()
                    WHERE id = %s AND tenant_id = %s
                """), draft_id, tenant_id)
        log.info("action=cfo_approve draft=%s tenant=%s by=%s", draft_id, tenant_id, user)
        return ok_response("CFO approval recorded", {"id": draft_id, "status": "approved", "approved_by": user, "level": "CFO"})
    except Exception as e:
        return http_error(500, str(e), "CFO_APPROVE_ERROR")


@router.get("/awaiting-cfo")
async def list_awaiting_cfo(request: Request):
    """List all drafts awaiting CFO second approval."""
    require_permission(request, "approval:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q("""
            SELECT id, date, description, partner, amount, currency, status, created_at
            FROM journal_drafts
            WHERE tenant_id = %s AND status = 'awaiting_cfo'
            ORDER BY amount DESC
        """), tenant_id)]
    for r in rows:
        r["date"] = str(r["date"])[:10] if r.get("date") else None
        r["created_at"] = str(r["created_at"])[:19] if r.get("created_at") else None
        r["amount"] = float(r["amount"] or 0)

    return ok_response("Drafts awaiting CFO approval", {"items": rows, "count": len(rows)})

