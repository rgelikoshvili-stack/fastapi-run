"""app/api/routes_rs_ge.py — RS.ge full integration routes (RS-1 + RS-2).

RS-1 (basic):    POST /rs-ge/waybill, GET /rs-ge/waybills, GET /rs-ge/types, etc.
RS-2 (test mode): auth, document sync, evidence, accounting drafts, test actions.

All RS.ge write actions require RSGE_TEST_MODE=true.
Production live mutations are always blocked.
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response
from app.api.services.rsge_config import mode_summary, require_test_mode, require_action_flag

log = logging.getLogger(__name__)
router = APIRouter(tags=["RS.ge"])


# ── Connector helper ──────────────────────────────────────────────────────────

def _connector(request: Request):
    """Build RsGeConnector, falling back to in-process credential cache if env vars absent."""
    tenant_id = getattr(request.state, "tenant_id", "default") or "default"
    from app.api.connectors.rs_ge_connector import RsGeConnector
    conn = RsGeConnector(tenant_id=tenant_id)
    if conn.mode == "demo":
        creds = _cred_cache.get(tenant_id, {})
        su = creds.get("su", "")
        sp = creds.get("sp", "")
        if su and sp:
            conn.su = su
            conn.sp = sp
            conn.un_id = creds.get("un_id", "")
            conn.mode = "live"
    return conn


# In-process cache: populated by auth/start so connector works without env vars.
# Survives request lifetime; lost on process restart (env vars take over on restart).
_cred_cache: dict = {}


def _tid(request: Request) -> str:
    return getattr(request.state, "tenant_id", "default") or "default"


def _actor(request: Request) -> str:
    return str(getattr(request.state, "user_id", "") or "")


# ═══════════════════════════════════════════════════════════════════════════════
# STATUS & MODE
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def rs_ge_status(request: Request):
    """RS.ge connector health + mode flags."""
    require_permission(request, "posting:read")
    conn_r = _connector(request)
    status = conn_r.status()
    return ok_response(
        "RS.ge სტატუსი",
        {**status, "mode_flags": mode_summary()},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════════════════════

class SoapAuthRequest(BaseModel):
    su: str = Field(..., description="RS.ge service username")
    sp: str = Field(..., description="RS.ge service password")
    skip_verify: bool = Field(False, description="Skip live credential check (test use only)")


class EapiAuthRequest(BaseModel):
    public_key: str
    secret_key: str


class VerifyPinRequest(BaseModel):
    pin_code: str = Field(..., description="SMS code received on masked mobile")


@router.post("/auth/start")
async def auth_start(body: SoapAuthRequest, request: Request):
    """Store RS.ge SOAP credentials (su/sp) in Credential Vault.

    Calls chek_service_user to verify, then encrypts and stores.
    Response never contains raw credentials.
    """
    require_permission(request, "settings:write")
    from app.api.db import get_conn
    from app.api.services.rsge_auth_service import start_soap_auth
    async with get_conn() as conn:
        result = await start_soap_auth(
            conn, _tid(request), body.su, body.sp,
            actor=_actor(request), skip_verify=body.skip_verify,
        )
    if result.get("connected"):
        # Populate in-process cache so connector works without env vars this session
        _cred_cache[_tid(request)] = {"su": body.su, "sp": body.sp,
                                       "un_id": result.get("un_id") or ""}
        return ok_response("RS.ge კავშირი დამყარდა", result)
    return error_response("RS.ge კავშირი ვერ დამყარდა", "AUTH_FAILED",
                          result.get("error", ""))


@router.post("/auth/eapi/start")
async def auth_eapi_start(body: EapiAuthRequest, request: Request):
    """Start RSoAuth/eAPI flow using PublicKey + SecretKey.

    Returns connected=True for one-step auth, or masked_mobile for PIN flow.
    Raw keys and tokens are never returned.
    """
    require_permission(request, "settings:write")
    from app.api.db import get_conn
    from app.api.services.rsge_auth_service import start_eapi_auth
    async with get_conn() as conn:
        result = await start_eapi_auth(
            conn,
            _tid(request),
            body.public_key,
            body.secret_key,
            actor=_actor(request),
        )
    if result.get("connected") or result.get("steps") == 2:
        return ok_response("RS.ge eAPI auth started", result)
    return error_response("RS.ge eAPI auth failed", "EAPI_AUTH_FAILED", result.get("error", ""))


@router.post("/auth/verify-pin")
async def auth_verify_pin(body: VerifyPinRequest, request: Request):
    """Complete two-step RSoAuth (eAPI): exchange PIN_TOKEN + SMS code for ACCESS_TOKEN."""
    require_permission(request, "settings:write")
    from app.api.db import get_conn
    from app.api.services.rsge_auth_service import verify_pin
    async with get_conn() as conn:
        result = await verify_pin(conn, _tid(request), body.pin_code, _actor(request))
    if result.get("connected"):
        return ok_response("RS.ge ორსაფეხურიანი ავტ. დასრულდა", result)
    return error_response("PIN ვერიფიკაცია ვერ მოხერხდა", "PIN_FAILED",
                          result.get("error", ""))


@router.post("/auth/signout")
async def auth_signout(request: Request):
    """Revoke stored RS.ge credentials for this tenant."""
    require_permission(request, "settings:write")
    from app.api.db import get_conn
    from app.api.services.rsge_auth_service import signout
    async with get_conn() as conn:
        result = await signout(conn, _tid(request), _actor(request))
    return ok_response("RS.ge კავშირი გაწყვეტილია", result)


@router.get("/auth/status")
async def auth_status(request: Request):
    """Return connection status without raw credentials."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn
    from app.api.services.rsge_auth_service import get_connection_status
    async with get_conn() as conn:
        result = await get_connection_status(conn, _tid(request))
    return ok_response("RS.ge კავშირის სტატუსი", result)


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENTS (invoices / tax docs)
# ═══════════════════════════════════════════════════════════════════════════════

class SyncSelectedRequest(BaseModel):
    rsge_ids: List[str] = Field(..., min_length=1, description="RS.ge document IDs to sync")
    own_inn: str = Field("", description="Tenant's own INN for direction detection")


class CreateDraftRequest(BaseModel):
    own_inn: str = Field("", description="Tenant's own INN for direction detection")


@router.get("/documents")
async def list_documents(request: Request, limit: int = 100, own_inn: str = ""):
    """List RS.ge invoices/tax documents with local sync status."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn
    from app.api.services.rsge_document_service import list_documents as _list
    async with get_conn() as conn:
        docs = await _list(conn, _tid(request), _connector(request), own_inn=own_inn, limit=limit)
    return ok_response(f"RS.ge დოკუმენტები ({len(docs)})",
                       {"documents": docs, "count": len(docs)})


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, request: Request):
    """Get a single synced RS.ge document by local DB id."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("SELECT * FROM rsge_documents WHERE id = %s AND tenant_id = %s"),
            doc_id, _tid(request),
        )
    if not row:
        return error_response("დოკუმენტი ვერ მოიძებნა", "NOT_FOUND", f"id={doc_id}")
    return ok_response("RS.ge დოკუმენტი", dict(row))


@router.get("/documents/{doc_id}/status")
async def get_document_status(doc_id: int, request: Request):
    """Get current RS.ge status of a synced document."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("SELECT rsge_id, rsge_status, rsge_status_code, synced_at "
               "FROM rsge_documents WHERE id = %s AND tenant_id = %s"),
            doc_id, _tid(request),
        )
    if not row:
        return error_response("დოკუმენტი ვერ მოიძებნა", "NOT_FOUND", f"id={doc_id}")
    return ok_response("RS.ge დოკუმენტის სტატუსი", dict(row))


@router.post("/documents/sync-selected")
async def sync_selected_documents(body: SyncSelectedRequest, request: Request):
    """Download and sync selected RS.ge documents to local DB."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_document_service import sync_selected, create_sync_job
    async with get_conn() as conn:
        job_id = await create_sync_job(conn, _tid(request), "document_sync", _actor(request))
        result = await sync_selected(
            conn, _tid(request), body.rsge_ids, _connector(request),
            own_inn=body.own_inn, actor=_actor(request), job_id=job_id,
        )
    return ok_response(
        f"სინქრონიზაცია: {result['synced_count']} დოკუმენტი",
        {**result, "job_id": job_id},
    )


@router.post("/documents/{doc_id}/create-evidence")
async def create_document_evidence(doc_id: int, request: Request):
    """Create an evidence record from a synced RS.ge document."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_document_service import create_evidence_from_document
    try:
        async with get_conn() as conn:
            result = await create_evidence_from_document(conn, _tid(request), doc_id, _actor(request))
        if result.get("duplicate"):
            return ok_response("Evidence უკვე არსებობს", result)
        return ok_response("Evidence შეიქმნა", result)
    except ValueError as exc:
        return error_response(str(exc), "NOT_FOUND", f"id={doc_id}")
    except Exception as exc:
        return error_response("Evidence შექმნა ვერ მოხერხდა", "EVIDENCE_ERROR", str(exc)[:200])


@router.post("/documents/{doc_id}/create-draft")
async def create_document_draft(doc_id: int, body: CreateDraftRequest, request: Request):
    """Create accounting journal draft suggestion from a synced document.

    Direction logic: buyer=own → purchase draft, seller=own → sales draft.
    Human must approve — no autonomous posting.
    """
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_document_service import create_draft_from_document
    try:
        async with get_conn() as conn:
            result = await create_draft_from_document(
                conn, _tid(request), doc_id, body.own_inn, _actor(request),
            )
        if result.get("duplicate"):
            return ok_response("დრაფტი უკვე არსებობს", result)
        return ok_response("სააღრიცხვო დრაფტი შეიქმნა", result)
    except ValueError as exc:
        return error_response(str(exc), "NOT_FOUND", f"id={doc_id}")
    except Exception as exc:
        return error_response("დრაფტი ვერ შეიქმნა", "DRAFT_ERROR", str(exc)[:200])


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT ACTIONS (test mode only)
# ═══════════════════════════════════════════════════════════════════════════════

class ActionRequest(BaseModel):
    approved_by: str = Field(..., description="User ID of Bridge Hub approver")
    comment: str = Field("", description="Optional comment (used for reject/correct)")


def _action_routes(action: str):
    """Factory for preview + execute route pair."""
    preview_path = f"/documents/{{doc_id}}/preview-{action}"
    execute_path = f"/documents/{{doc_id}}/test-{action}"

    @router.post(preview_path, name=f"rsge_preview_{action}")
    async def _preview(doc_id: int, request: Request):
        f"""Preview RS.ge test-{action} action without executing."""
        require_permission(request, "posting:write")
        from app.api.db import get_conn
        from app.api.services.rsge_action_service import preview_action
        async with get_conn() as conn:
            result = await preview_action(conn, _tid(request), doc_id, action)
        if not result.get("valid"):
            return error_response("Preview ვერ გენერირდა", "PREVIEW_ERROR",
                                  result.get("error", ""))
        return ok_response(f"RS.ge {action} preview", result)

    @router.post(execute_path, name=f"rsge_test_{action}")
    async def _execute(doc_id: int, body: ActionRequest, request: Request):
        f"""Execute RS.ge test-{action} action (TEST MODE only)."""
        require_permission(request, "posting:write")
        require_action_flag(action)
        from app.api.db import get_conn
        from app.api.services.rsge_action_service import execute_test_action
        try:
            async with get_conn() as conn:
                result = await execute_test_action(
                    conn, _tid(request), doc_id, action,
                    requested_by=_actor(request),
                    approved_by=body.approved_by,
                    connector=_connector(request),
                    comment=body.comment,
                )
            if result.get("success"):
                return ok_response(f"RS.ge test-{action} შესრულდა", result)
            return error_response(f"RS.ge test-{action} ვერ შესრულდა",
                                  "ACTION_FAILED", result.get("error") or "")
        except ValueError as exc:
            return error_response(str(exc), "INVALID_REQUEST", "")


for _act in ("confirm", "reject", "correct", "cancel"):
    _action_routes(_act)


# ═══════════════════════════════════════════════════════════════════════════════
# WAYBILLS / ზედნადებები
# ═══════════════════════════════════════════════════════════════════════════════

class WaybillSyncRequest(BaseModel):
    waybill_ids: List[str] = Field(..., min_length=1)


@router.get("/waybills")
async def list_waybills(request: Request, limit: int = 50):
    """List RS.ge waybills with local sync status."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn
    from app.api.services.rsge_waybill_service import list_waybills as _list
    async with get_conn() as conn:
        items = await _list(conn, _tid(request), _connector(request), limit=limit)
    return ok_response(f"ზედნადებები ({len(items)})",
                       {"waybills": items, "count": len(items)})


@router.get("/waybills/{waybill_id}")
async def get_waybill(waybill_id: int, request: Request):
    """Get a single synced waybill from local DB."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("SELECT * FROM rsge_waybills WHERE id = %s AND tenant_id = %s"),
            waybill_id, _tid(request),
        )
    if not row:
        # Fallback: try to fetch from RS.ge directly
        result = _connector(request).get_waybill(waybill_id)
        if "error" in result:
            return error_response("ზედნადები ვერ მოიძებნა", "NOT_FOUND",
                                  f"id={waybill_id}")
        return ok_response("ზედნადები (RS.ge live)", result)
    return ok_response("ზედნადები", dict(row))


@router.post("/waybills/sync-selected")
async def sync_selected_waybills(body: WaybillSyncRequest, request: Request):
    """Download and sync selected waybills to local DB."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_waybill_service import sync_selected
    async with get_conn() as conn:
        result = await sync_selected(
            conn, _tid(request), body.waybill_ids, _connector(request), _actor(request),
        )
    return ok_response(
        f"ზედნადებები სინქრ.: {result['synced_count']}",
        result,
    )


@router.post("/waybills/{waybill_id}/create-evidence")
async def create_waybill_evidence(waybill_id: int, request: Request):
    """Create evidence record from a synced waybill."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_waybill_service import create_evidence_from_waybill
    try:
        async with get_conn() as conn:
            result = await create_evidence_from_waybill(conn, _tid(request), waybill_id, _actor(request))
        if result.get("duplicate"):
            return ok_response("Evidence უკვე არსებობს", result)
        return ok_response("ზედნადები Evidence შეიქმნა", result)
    except ValueError as exc:
        return error_response(str(exc), "NOT_FOUND", f"id={waybill_id}")
    except Exception as exc:
        return error_response("Evidence შექმნა ვერ მოხერხდა", "EVIDENCE_ERROR", str(exc)[:200])


# Waybill test actions (activate, cancel)
@router.post("/waybills/{waybill_id}/preview-activate")
async def preview_activate_waybill(waybill_id: int, request: Request):
    """Preview activate action for a saved waybill."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_action_service import preview_action
    async with get_conn() as conn:
        result = await preview_action(conn, _tid(request), waybill_id, "activate", "waybill")
    if not result.get("valid"):
        return error_response("Preview ვერ გენერირდა", "PREVIEW_ERROR", result.get("error", ""))
    return ok_response("ზედნადები activate preview", result)


@router.post("/waybills/{waybill_id}/test-activate")
async def test_activate_waybill(waybill_id: int, body: ActionRequest, request: Request):
    """Activate a saved waybill on RS.ge test account."""
    require_permission(request, "posting:write")
    require_action_flag("activate")
    from app.api.db import get_conn
    from app.api.services.rsge_action_service import execute_test_action
    async with get_conn() as conn:
        result = await execute_test_action(
            conn, _tid(request), waybill_id, "activate",
            requested_by=_actor(request), approved_by=body.approved_by,
            connector=_connector(request), doc_type="waybill",
        )
    if result.get("success"):
        return ok_response("ზედნადები გააქტიურდა", result)
    return error_response("ზედნადების გააქტიურება ვერ მოხერხდა", "ACTION_FAILED",
                          result.get("error") or "")


@router.post("/waybills/{waybill_id}/preview-cancel")
async def preview_cancel_waybill(waybill_id: int, request: Request):
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_action_service import preview_action
    async with get_conn() as conn:
        result = await preview_action(conn, _tid(request), waybill_id, "cancel", "waybill")
    if not result.get("valid"):
        return error_response("Preview ვერ გენერირდა", "PREVIEW_ERROR", result.get("error", ""))
    return ok_response("ზედნადები cancel preview", result)


@router.post("/waybills/{waybill_id}/test-cancel")
async def test_cancel_waybill(waybill_id: int, body: ActionRequest, request: Request):
    require_permission(request, "posting:write")
    require_action_flag("cancel")
    from app.api.db import get_conn
    from app.api.services.rsge_action_service import execute_test_action
    async with get_conn() as conn:
        result = await execute_test_action(
            conn, _tid(request), waybill_id, "cancel",
            requested_by=_actor(request), approved_by=body.approved_by,
            connector=_connector(request), doc_type="waybill",
        )
    if result.get("success"):
        return ok_response("ზედნადები გაუქმდა", result)
    return error_response("გაუქმება ვერ მოხერხდა", "ACTION_FAILED", result.get("error") or "")


# ═══════════════════════════════════════════════════════════════════════════════
# RS-1 WAYBILL SUBMIT (create new waybill to RS.ge)
# ═══════════════════════════════════════════════════════════════════════════════

class GoodsItem(BaseModel):
    id: int = 0
    name: str
    unit_id: int = 1
    unit_txt: str = ""
    quantity: float
    price: float
    amount: float = 0.0
    bar_code: str = ""
    akciz_id: int = 0
    vat_type: int = 1
    quantity_ext: float = 0.0


class WaybillSubmitRequest(BaseModel):
    id: int = 0
    type: int = 2
    buyer_tin: str
    buyer_name: str = ""
    check_buyer_tin: int = 1
    start_address: str
    end_address: str
    driver_tin: str = ""
    driver_name: str = ""
    check_driver_tin: int = 1
    car_number: str = ""
    transport_cost: float = 0.0
    tran_cost_payer: int = 1
    trans_id: int = 1
    reception_info: str = ""
    receiver_info: str = ""
    full_amount: float = 0.0
    comment: str = ""
    begin_date: Optional[str] = None
    goods_list: List[GoodsItem] = Field(..., min_length=1)


@router.post("/waybill/validate")
async def validate_waybill(body: WaybillSubmitRequest, request: Request):
    """Validate waybill draft fields without submitting."""
    require_permission(request, "posting:read")
    draft = body.model_dump()
    draft["goods_list"] = [g.model_dump() for g in body.goods_list]
    result = _connector(request).preview(draft)
    if result["valid"]:
        return ok_response("ზედნადები მზადაა გასაგზავნად", result)
    return error_response("ზედნადებში შეცდომებია", "VALIDATION_FAILED", result)


@router.post("/waybill")
async def submit_waybill(body: WaybillSubmitRequest, request: Request):
    """Create and submit a new waybill to RS.ge."""
    require_permission(request, "posting:write")
    require_test_mode("submit_waybill")
    conn_r = _connector(request)
    draft = body.model_dump()
    draft["goods_list"] = [g.model_dump() for g in body.goods_list]
    for g in draft["goods_list"]:
        if not g.get("amount") or float(g.get("amount", 0)) == 0:
            g["amount"] = round(float(g["quantity"]) * float(g["price"]), 4)
    if not draft.get("full_amount") or float(draft.get("full_amount", 0)) == 0:
        draft["full_amount"] = round(
            sum(float(g.get("amount", 0)) for g in draft["goods_list"]), 4
        )
    result = conn_r.post(draft)
    if result.get("success"):
        return ok_response("ზედნადები წარმატებით გაიგზავნა RS.ge-ზე",
                           {"waybill_id": result.get("erp_id"), "mode": conn_r.mode})
    return error_response("ზედნადების გაგზავნა ვერ მოხერხდა", "RS_GE_ERROR",
                          str(result.get("error", "")))


# ═══════════════════════════════════════════════════════════════════════════════
# INVOICE
# ═══════════════════════════════════════════════════════════════════════════════

class InvoiceSubmitRequest(BaseModel):
    user_id: str = ""
    invoice_id: int = 0
    operation_date: Optional[str] = None
    seller_un_id: str = ""
    buyer_un_id: str
    overhead_no: str = ""
    overhead_dt: Optional[str] = None
    b_s_user_id: str = ""


@router.post("/invoice")
async def submit_invoice(body: InvoiceSubmitRequest, request: Request):
    """Submit a tax invoice to RS.ge."""
    require_permission(request, "posting:write")
    require_test_mode("submit_invoice")
    conn_r = _connector(request)
    result = conn_r.save_invoice(body.model_dump())
    if result.get("success"):
        return ok_response("ინვოისი წარმატებით გაიგზავნა RS.ge-ზე",
                           {"invoice_id": result.get("erp_id"), "mode": conn_r.mode})
    return error_response("ინვოისის გაგზავნა ვერ მოხერხდა", "RS_GE_ERROR",
                          str(result.get("error", "")))


@router.get("/invoices")
async def list_invoices_from_rsge(request: Request, limit: int = 50):
    """Fetch invoices directly from RS.ge service."""
    require_permission(request, "posting:read")
    conn_r = _connector(request)
    items = conn_r.get_user_invoices(limit=limit)
    return ok_response(f"ინვოისები ({len(items)})", {"invoices": items, "count": len(items)})


# ═══════════════════════════════════════════════════════════════════════════════
# TAXPAYER VERIFICATION
# ═══════════════════════════════════════════════════════════════════════════════

class TaxpayerRequest(BaseModel):
    inn: str


@router.get("/taxpayers/{inn}")
async def verify_taxpayer_get(inn: str, request: Request):
    """Verify taxpayer INN via RS.ge public REST API."""
    require_permission(request, "posting:read")
    result = _connector(request).verify_taxpayer(inn)
    if result.get("valid"):
        return ok_response("გადასახადის გადამხდელი ვალიდურია", result)
    return ok_response("გადასახადის გადამხდელი არ მოიძებნა", result)


@router.post("/taxpayer/verify")
async def verify_taxpayer_post(body: TaxpayerRequest, request: Request):
    """Verify taxpayer INN (POST form)."""
    require_permission(request, "posting:read")
    result = _connector(request).verify_taxpayer(body.inn)
    if result.get("valid"):
        return ok_response("გადასახადის გადამხდელი ვალიდურია", result)
    return ok_response("გადასახადის გადამხდელი არ მოიძებნა", result)


# ═══════════════════════════════════════════════════════════════════════════════
# LOOKUP TABLES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/types")
async def rs_ge_types(request: Request):
    require_permission(request, "posting:read")
    return ok_response("ზედნადების ტიპები",
                       {"types": _connector(request).get_waybill_types()})


@router.get("/units")
async def rs_ge_units(request: Request):
    require_permission(request, "posting:read")
    return ok_response("საზომი ერთეულები",
                       {"units": _connector(request).get_waybill_units()})
