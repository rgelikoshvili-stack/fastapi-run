import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Path, Query, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.tenant_context import resolve_tenant_id
from app.api.authz import require_permission
from app.api.security import limiter

from app.api.services.posting_service import (
    get_approved_drafts_service,
    get_posting_payload_service,
    mock_posting_service,
    get_posting_logs_service,
    get_posting_log_detail_service,
    get_balance_status_service,
    post_draft_to_balance_service,
    get_onec_status_service,
    post_draft_to_onec_service,
    get_oris_status_service,
    post_draft_to_oris_service,
    apply_posting_service,
    dry_run_posting_service,
)
from app.api.services.posting_preview_service import preview_posting_service
from app.api.services.idempotency_service import idempotency_check, idempotency_store

router = APIRouter(prefix="/posting", tags=["posting"])


# ===============================
# VALIDATION
# ===============================
def _validate_pagination(limit: int, offset: int):
    if limit < 0:
        raise HTTPException(status_code=422, detail="invalid limit")
    if offset < 0:
        raise HTTPException(status_code=422, detail="invalid offset")


# ===============================
# READ ENDPOINTS
# ===============================
@router.get("/approved-drafts")
async def get_approved_drafts(
    request: Request,
    limit: int = Query(100),
    offset: int = Query(0),
):
    require_permission(request, "posting:read")

    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    return await get_approved_drafts_service(limit=limit, offset=offset, tenant_id=tenant_id)


@router.get("/payload/{draft_id}")
async def get_posting_payload(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_posting_payload_service(draft_id=draft_id, tenant_id=tenant_id)


@router.get("/logs")
async def get_posting_logs(
    request: Request,
    limit: int = Query(100),
    offset: int = Query(0),
    target_system: str | None = Query(None),
    draft_id: int | None = Query(None),
):
    require_permission(request, "posting:read")

    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    return await get_posting_logs_service(
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        target_system=target_system,
        draft_id=draft_id,
    )


@router.get("/logs/{log_id}")
async def get_posting_log_detail(
    request: Request,
    log_id: int = Path(...),
):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await get_posting_log_detail_service(log_id=log_id, tenant_id=tenant_id)


@router.get("/history")
async def get_posting_history(
    request: Request,
    limit: int = Query(100),
    offset: int = Query(0),
    target_system: str | None = Query(None),
    draft_id: int | None = Query(None),
):
    require_permission(request, "posting:read")

    _validate_pagination(limit, offset)
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    return await get_posting_logs_service(
        limit=limit,
        offset=offset,
        tenant_id=tenant_id,
        target_system=target_system,
        draft_id=draft_id,
    )


# ===============================
# STATUS (READ)
# ===============================
@router.get("/balance-status")
def get_balance_status(request: Request):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_balance_status_service(tenant_id=tenant_id)


@router.get("/onec-status")
def get_onec_status(request: Request):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_onec_status_service(tenant_id=tenant_id)


@router.get("/oris-status")
def get_oris_status(request: Request):
    require_permission(request, "posting:read")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return get_oris_status_service(tenant_id=tenant_id)


# ===============================
# SHADOW POSTING (read-only preview)
# ===============================
@router.get("/preview/{draft_id}")
async def preview_posting(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await preview_posting_service(draft_id=draft_id, tenant_id=tenant_id)


# ===============================
# WRITE ENDPOINTS
# ===============================
@router.post("/mock/{draft_id}")
@limiter.limit("20/minute")
async def mock_posting(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", None)
    return await mock_posting_service(draft_id=draft_id, tenant_id=tenant_id, actor=actor)


@router.post("/balance/{draft_id}")
@limiter.limit("20/minute")
async def post_draft_to_balance(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", None)
    return await post_draft_to_balance_service(draft_id=draft_id, tenant_id=tenant_id, actor=actor)


@router.post("/balance/dry-run/{draft_id}")
@limiter.limit("30/minute")
async def dry_run_balance(
    request: Request,
    draft_id: int = Path(...),
):
    """Dry-run Balance.ge posting — builds payload, logs result, makes no ERP call.

    Gate 6 (Balance.ge activation checklist): this endpoint must succeed before
    any live /posting/balance/{draft_id} call is made on a production tenant.
    """
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", None)
    idem_key = request.headers.get("X-Idempotent-Key")
    if idem_key:
        hit = await idempotency_check(tenant_id, idem_key, f"dry_run:{draft_id}:balance")
        if hit is not None:
            return hit
    result = await dry_run_posting_service(
        draft_id=draft_id,
        target="balance",
        tenant_id=tenant_id,
        actor=actor,
    )
    if idem_key:
        await idempotency_store(tenant_id, idem_key, f"dry_run:{draft_id}:balance", result)
    return result


@router.post("/onec/{draft_id}")
@limiter.limit("20/minute")
async def post_draft_to_onec(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", None)
    return await post_draft_to_onec_service(draft_id=draft_id, tenant_id=tenant_id, actor=actor)


@router.post("/oris/{draft_id}")
@limiter.limit("20/minute")
async def post_draft_to_oris(
    request: Request,
    draft_id: int = Path(...),
):
    require_permission(request, "posting:write")

    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    actor = getattr(request.state, "user_id", None)
    return await post_draft_to_oris_service(draft_id=draft_id, tenant_id=tenant_id, actor=actor)


@router.post("/apply/{draft_id}")
@limiter.limit("20/minute")
async def apply_posting(
    request: Request,
    draft_id: int = Path(...),
    target: str = Query(...),
    force: bool = Query(False),
):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    idem_key = request.headers.get("X-Idempotent-Key")
    if idem_key:
        hit = await idempotency_check(tenant_id, idem_key, f"posting:{draft_id}:{target}")
        if hit is not None:
            return hit
    actor = getattr(request.state, "user_id", None)
    result = await apply_posting_service(draft_id=draft_id, target=target, tenant_id=tenant_id, force=force, actor=actor)
    if idem_key:
        await idempotency_store(tenant_id, idem_key, f"posting:{draft_id}:{target}", result)
    return result


# ===============================
# MANUAL FALLBACK — Gate 12
# ===============================

@router.get("/export/approved-drafts/csv")
async def export_approved_drafts_csv(
    request: Request,
    limit: int = Query(500),
    offset: int = Query(0),
):
    """Export approved (unposted) drafts as CSV for manual Balance.ge upload.

    Intended for use when the Balance.ge connector is disabled (CONNECTOR_DISABLED
    rollback scenario) and an accountant needs to enter journals manually.
    Requires posting:read permission. Returns CSV with one row per journal line.
    """
    require_permission(request, "posting:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    _validate_pagination(limit, offset)

    from app.api.db import get_conn, _q
    from app.api.services.posting_service import _normalize_lines

    async with get_conn() as conn:
        rows = await conn.fetch(_q("""
            SELECT id, date, description, partner,
                   COALESCE(amount, 0) AS amount,
                   COALESCE(currency, 'GEL') AS currency,
                   COALESCE(lines_json, '[]'::jsonb) AS lines_json
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status = 'approved'
            ORDER BY date DESC, id DESC
            LIMIT %s OFFSET %s
        """), tenant_id, limit, offset)

    output = io.StringIO()
    fieldnames = ["draft_id", "date", "description", "partner",
                  "draft_amount", "currency", "line_no",
                  "account_code", "debit", "credit", "label"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        lines = _normalize_lines(row["lines_json"] or [])
        for idx, line in enumerate(lines, start=1):
            writer.writerow({
                "draft_id":     row["id"],
                "date":         str(row["date"] or ""),
                "description":  row["description"] or "",
                "partner":      row["partner"] or "",
                "draft_amount": float(row["amount"] or 0),
                "currency":     row["currency"] or "GEL",
                "line_no":      idx,
                "account_code": line.get("account_code", ""),
                "debit":        float(line.get("debit", 0) or 0),
                "credit":       float(line.get("credit", 0) or 0),
                "label":        line.get("label", ""),
            })

    output.seek(0)
    filename = f"approved_drafts_{tenant_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/connector/{target}/disable")
async def disable_connector(
    request: Request,
    target: str = Path(...),
):
    """Disable a connector for this tenant (Gate 12 rollback).

    Sets connector.<target>_enabled=false in tenant_settings.
    All subsequent live posting calls will return CONNECTOR_DISABLED.
    Use POST /connector/{target}/enable to re-enable.
    Requires posting:write permission.
    """
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    from app.api.services.tenant_config_service import set_tenant_setting
    await set_tenant_setting(tenant_id, f"connector.{target}_enabled", False)
    return {
        "ok": True,
        "message": f"{target} connector disabled for tenant {tenant_id}",
        "data": {"target": target, "enabled": False, "tenant_id": tenant_id},
        "error": None,
    }


@router.post("/connector/{target}/enable")
async def enable_connector(
    request: Request,
    target: str = Path(...),
):
    """Re-enable a previously disabled connector (Gate 12 rollback recovery).

    Sets connector.<target>_enabled=true in tenant_settings.
    Requires posting:write permission.
    """
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    from app.api.services.tenant_config_service import set_tenant_setting
    await set_tenant_setting(tenant_id, f"connector.{target}_enabled", True)
    return {
        "ok": True,
        "message": f"{target} connector enabled for tenant {tenant_id}",
        "data": {"target": target, "enabled": True, "tenant_id": tenant_id},
        "error": None,
    }