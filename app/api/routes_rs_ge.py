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

async def _connector_async(request: Request):
    """Build RsGeConnector: env vars → in-process cache → vault (persistent)."""
    tenant_id = getattr(request.state, "tenant_id", "default") or "default"
    from app.api.connectors.rs_ge_connector import RsGeConnector
    conn = RsGeConnector(tenant_id=tenant_id)
    if conn.mode == "demo":
        creds = _cred_cache.get(tenant_id, {})
        if not creds:
            try:
                from app.api.db import get_conn
                from app.api.services.rsge_auth_service import load_connector_creds
                async with get_conn() as db_conn:
                    creds = await load_connector_creds(db_conn, tenant_id)
                if creds.get("su") and creds.get("sp"):
                    _cred_cache[tenant_id] = creds
            except Exception:
                creds = {}
        su = creds.get("su", "")
        sp = creds.get("sp", "")
        if su and sp:
            conn.su = su
            conn.sp = sp
            conn.un_id = creds.get("un_id", "")
            conn.mode = "live"
    return conn


def _connector(request: Request):
    """Sync shim — use _connector_async in async routes."""
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


# In-process cache: populated by auth/start or vault load.
# Lost on process restart; vault provides persistent fallback.
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
    conn_r = await _connector_async(request)
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
    try:
        async with get_conn() as conn:
            result = await start_soap_auth(
                conn, _tid(request), body.su, body.sp,
                actor=_actor(request), skip_verify=body.skip_verify,
            )
    except Exception as exc:
        log.exception("[RS.GE] auth_start vault error tenant=%s", _tid(request))
        return error_response(
            "RS.ge კავშირი ვერ შეიქმნა (vault error)",
            "VAULT_ERROR",
            "Credential vault operation failed",
        )
    if result.get("connected"):
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
        docs = await _list(conn, _tid(request), await _connector_async(request), own_inn=own_inn, limit=limit)
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
            conn, _tid(request), body.rsge_ids, await _connector_async(request),
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
                    connector=await _connector_async(request),
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


@router.post("/documents/{doc_id}/create-correction-draft")
async def create_correction_draft(doc_id: int, request: Request):
    """Suggest a correction journal draft for a RS.ge corrected document (no auto-post)."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_document_service import create_correction_draft_suggestion
    try:
        async with get_conn() as conn:
            result = await create_correction_draft_suggestion(conn, _tid(request), doc_id, _actor(request))
        return ok_response("კ. დ. შ.", result)
    except ValueError as exc:
        return error_response(str(exc), "NOT_FOUND", f"id={doc_id}")
    except Exception as exc:
        return error_response("კ. ვ. შ.", "DRAFT_ERROR", str(exc)[:200])


@router.post("/documents/{doc_id}/create-reversal-draft")
async def create_reversal_draft(doc_id: int, request: Request):
    """Suggest a cancellation/reversal draft for a RS.ge cancelled document (no auto-post)."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_document_service import create_cancellation_reversal_draft
    try:
        async with get_conn() as conn:
            result = await create_cancellation_reversal_draft(conn, _tid(request), doc_id, _actor(request))
        return ok_response("გ. დ. შ.", result)
    except ValueError as exc:
        return error_response(str(exc), "NOT_FOUND", f"id={doc_id}")
    except Exception as exc:
        return error_response("გ. ვ. შ.", "DRAFT_ERROR", str(exc)[:200])


# ═══════════════════════════════════════════════════════════════════════════════
# WAYBILLS / ზედნადებები
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/debug/buyer-waybills")
async def debug_buyer_waybills(request: Request):
    """Return raw SOAP response from get_buyer_waybills for debugging."""
    require_permission(request, "posting:read")
    import xml.etree.ElementTree as ET
    from app.api.connectors.rs_ge_connector import (
        _soap_call, _WB_NS, _WAYBILL_WSDL, _result_xml, _xml_text, _local_name
    )
    from datetime import datetime, timezone
    connector = await _connector_async(request)
    if connector.mode != "live":
        return ok_response("demo mode — no SOAP call", {"mode": "demo"})
    try:
        end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        resp = _soap_call(
            _WAYBILL_WSDL, "get_buyer_waybills", _WB_NS,
            {"su": connector.su, "sp": connector.sp,
             "create_date_s": "2020-01-01T00:00:00",
             "create_date_e": end,
             "itypes": "", "seller_tin": "", "statuses": "",
             "car_number": "", "driver_tin": "", "waybill_number": "",
             "s_user_ids": "", "comment": ""}
        )
        raw_xml = ET.tostring(resp, encoding="unicode")
        payload = _result_xml(resp, "get_buyer_waybillsResult")
        status_code = _xml_text(payload, "STATUS")
        all_tags = sorted({_local_name(t.tag) for t in resp.iter()})
        # Find all potential waybill elements
        waybill_tags = [_local_name(t.tag) for t in payload.iter()
                        if _local_name(t.tag) not in
                        ("get_buyer_waybillsResult", "RESULT", "STATUS", "GOODS_LIST")]
        return ok_response("raw buyer waybills response", {
            "xml_preview": raw_xml[:4000],
            "all_tags": all_tags,
            "status_code": status_code,
            "waybill_candidate_tags": waybill_tags[:50],
            "mode": connector.mode,
        })
    except Exception as exc:
        return error_response("SOAP call failed", "SOAP_ERROR", str(exc)[:500])

class WaybillSyncRequest(BaseModel):
    waybill_ids: List[str] = Field(..., min_length=1)


class WaybillByNumberRequest(BaseModel):
    waybill_number: str = Field(..., min_length=1)


class WaybillDraftRequest(BaseModel):
    debit_account: str = Field(..., description="Debit account code e.g. 1310")
    credit_account: str = Field(..., description="Credit account code e.g. 3110")
    description: Optional[str] = None
    own_tin: Optional[str] = ""
    amount_override: Optional[float] = None   # User-edited total (may include extra services)
    lines: Optional[List[Dict[str, Any]]] = None  # Edited goods lines for memo
    vat_split: bool = False          # If True: build 3-line Dr(net)/Dr(VAT)/Cr entry
    vat_rate: float = 18.0           # VAT % (18 for standard Georgian VAT)
    vat_account: str = "3311"        # VAT receivable account


class PartnerMapRequest(BaseModel):
    tin: str = Field(..., min_length=1)
    partner_name: Optional[str] = None
    account_code: str = Field(..., min_length=1)
    notes: Optional[str] = None


class ItemMapRequest(BaseModel):
    item_code: str = Field(..., min_length=1)
    item_name: Optional[str] = None
    account_code: str = Field(..., min_length=1)
    vat_exempt: bool = False


class SuggestDraftRequest(BaseModel):
    seller_tin: Optional[str] = None
    goods_list: Optional[List[Dict[str, Any]]] = None


class WaybillMetaUpdate(BaseModel):
    begin_date: Optional[str] = None
    full_amount: Optional[float] = None
    goods_list: Optional[List[Dict[str, Any]]] = None


@router.get("/waybills")
async def list_waybills(request: Request, limit: int = 50,
                        date_from: str = "", date_to: str = ""):
    """List RS.ge waybills (sent + received) with local sync status."""
    require_permission(request, "posting:read")
    import json as _json
    from app.api.db import get_conn
    from app.api.services.rsge_waybill_service import list_waybills as _list
    connector = await _connector_async(request)
    soap_error: Optional[str] = None
    items: List[dict] = []
    try:
        async with get_conn() as conn:
            items = await _list(conn, _tid(request), connector, limit=limit,
                                date_from=date_from, date_to=date_to)
    except Exception as exc:
        log.warning("[RS.GE] list_waybills SOAP error tenant=%s: %s", _tid(request), exc)
        soap_error = str(exc)[:400]

    # Fetch received (buyer) waybills via dedicated RS.ge buyer endpoint
    received: List[dict] = []
    received_error: Optional[str] = None
    if connector.mode == "live":
        try:
            received = connector.get_received_waybills(limit=limit)
        except Exception as exc:
            log.warning("[RS.GE] get_buyer_waybills error tenant=%s: %s", _tid(request), exc)
            received_error = str(exc)[:400]

    all_items = items + received

    # Also include locally synced waybills not in SOAP results (e.g. received WBs synced by number)
    existing_nums = {w.get("waybill_number") for w in all_items if w.get("waybill_number")}
    try:
        async with get_conn() as conn:
            q = ("SELECT id, rsge_id, waybill_number, rsge_status, buyer_tin, buyer_name, "
                 "seller_name, seller_tin, full_amount, begin_date, draft_id, draft_status, raw_payload "
                 "FROM rsge_waybills WHERE tenant_id = $1")
            params: list = [_tid(request)]
            # Waybills with NULL begin_date (e.g. received WBs synced when SOAP returned empty dates)
            # are always included. Date filter applies only to non-null begin_dates.
            if date_from or date_to:
                date_conds = []
                if date_from:
                    params.append(date_from)
                    date_conds.append(f"begin_date >= ${len(params)}::timestamptz")
                if date_to:
                    params.append(date_to)
                    date_conds.append(f"begin_date <= ${len(params)}::timestamptz")
                q += f" AND (begin_date IS NULL OR ({' AND '.join(date_conds)}))"
            q += " ORDER BY begin_date DESC NULLS LAST LIMIT 200"
            db_rows = await conn.fetch(q, *params)
            for row in db_rows:
                wnum = row["waybill_number"] or ""
                if wnum and wnum in existing_nums:
                    continue
                raw_p = _json.loads(row["raw_payload"] or "{}")
                all_items.append({
                    "rsge_id":        row["rsge_id"] or "",
                    "waybill_number": wnum,
                    "rsge_status":    row["rsge_status"] or "",
                    "buyer_tin":      row["buyer_tin"] or "",
                    "buyer_name":     row["buyer_name"] or "",
                    "seller_name":    row["seller_name"] or raw_p.get("seller_name", ""),
                    "seller_tin":     row["seller_tin"] or raw_p.get("seller_tin", ""),
                    "full_amount":    float(row["full_amount"] or 0),
                    "begin_date":     str(row["begin_date"] or ""),
                    "source":         "db",
                    "synced":         True,
                    "local_id":       row["id"],
                    "draft_id":       row["draft_id"],
                    "draft_status":   row["draft_status"],
                    "direction":      raw_p.get("direction", "received"),
                })
                existing_nums.add(wnum)
    except Exception as exc:
        log.debug("[RS.GE] db waybill merge skipped tenant=%s: %s", _tid(request), exc)

    return ok_response(
        f"ზედნადებები ({len(all_items)})",
        {
            "waybills": all_items,
            "count": len(all_items),
            "sent_count": len(items),
            "received_count": len(received),
            "mode": connector.mode,
            "soap_error": soap_error,
            "received_error": received_error,
        },
    )


@router.get("/waybills/by-number")
async def get_waybill_by_number(number: str, request: Request):
    """Fetch any RS.ge waybill by its public waybill number — works for received waybills."""
    require_permission(request, "posting:read")
    if not number or not number.strip():
        return error_response("ზედნადების ნომერი სავალდებულოა", "MISSING_PARAM", "number")
    connector = await _connector_async(request)
    result = connector.get_waybill_by_number(number.strip())
    if "error" in result:
        return error_response("ზედნადები ვერ მოიძებნა", "NOT_FOUND", result["error"])
    return ok_response(f"ზედნადები #{number}", result)


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
        result = await _connector_async(request).get_waybill(waybill_id)
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
            conn, _tid(request), body.waybill_ids, await _connector_async(request), _actor(request),
        )
    return ok_response(
        f"ზედნადებები სინქრ.: {result['synced_count']}",
        result,
    )


@router.post("/waybills/sync-by-number")
async def sync_waybill_by_number(body: WaybillByNumberRequest, request: Request):
    """Fetch a waybill by its public number from RS.ge and sync to local DB.

    Works for received/buyer waybills where get_buyer_waybills returns STATUS=-100.
    """
    require_permission(request, "posting:write")
    connector = await _connector_async(request)
    result = connector.get_waybill_by_number(body.waybill_number.strip())
    if "error" in result:
        return error_response("ზედნადები ვერ მოიძებნა RS.ge-ზე", "NOT_FOUND", result["error"])

    from app.api.db import get_conn
    from app.api.services.rsge_waybill_service import _map_wb_to_dict, _upsert_waybill
    wb = _map_wb_to_dict(result)
    if not wb.get("rsge_id"):
        wb["rsge_id"] = f"bynumber_{body.waybill_number.strip()}"
    try:
        async with get_conn() as conn:
            local_id = await _upsert_waybill(conn, _tid(request), wb, result)
        return ok_response(
            f"ზედნადები #{body.waybill_number} სინქრ. ✓",
            {"local_id": local_id, "rsge_id": wb["rsge_id"],
             "waybill_number": wb["waybill_number"],
             "full_amount": wb["full_amount"],
             "seller_name": result.get("seller_name", ""),
             "synced": True},
        )
    except Exception as exc:
        log.warning("[RS.GE] sync-by-number failed number=%s: %s", body.waybill_number, exc)
        return error_response("სინქრ. ვერ მოხერხდა", "SYNC_ERROR", str(exc)[:200])


@router.post("/waybills/{waybill_id}/create-draft")
async def create_waybill_draft(waybill_id: int, body: WaybillDraftRequest, request: Request):
    """Create a journal draft from a synced waybill with custom debit/credit accounts."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn, _q
    from datetime import date as _date
    import json as _json
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                _q("SELECT * FROM rsge_waybills WHERE id = %s AND tenant_id = %s"),
                waybill_id, _tid(request),
            )
            if not row:
                return error_response("ზედნადები ვერ მოიძებნა", "NOT_FOUND", f"id={waybill_id}")
            wb = dict(row)
            # Use user-edited amount if provided, else fall back to waybill amount
            amount = body.amount_override if body.amount_override else float(wb.get("full_amount") or 0)
            wb_ref = wb.get('waybill_number') or wb.get('rsge_id')
            desc = (body.description or
                    f"RS.ge ზედნადები #{wb_ref} — {wb.get('buyer_name') or ''}")
            # Append edited lines summary to description if provided
            if body.lines:
                line_parts = [f"{l.get('name','')} {l.get('qty','')} × {l.get('amt','')}"
                              for l in body.lines if l.get('name')]
                if line_parts:
                    desc = desc + " | " + "; ".join(line_parts[:5])
            doc_date = str(wb.get("begin_date") or _date.today().isoformat())[:10]
            amt_r = round(float(amount), 2)
            if body.vat_split and amt_r > 0:
                rate = body.vat_rate or 18.0
                vat_amt = round(amt_r * rate / (100.0 + rate), 2)
                net_amt = round(amt_r - vat_amt, 2)
                lines_json_val = _json.dumps([
                    {"account_code": body.debit_account, "debit": net_amt, "credit": 0.0},
                    {"account_code": body.vat_account or "3311", "debit": vat_amt, "credit": 0.0},
                    {"account_code": body.credit_account, "debit": 0.0, "credit": amt_r},
                ])
            else:
                lines_json_val = _json.dumps([
                    {"account_code": body.debit_account, "debit": amt_r, "credit": 0.0},
                    {"account_code": body.credit_account, "debit": 0.0, "credit": amt_r},
                ])
            draft_row = await conn.fetchrow(
                _q("""INSERT INTO journal_drafts
                       (tenant_id, description, amount, debit_account, credit_account,
                        date, status, partner, reason, source_type, confidence, lines_json)
                     VALUES (%s,%s,%s,%s,%s,%s,'drafted',%s,%s,'rs_ge_waybill',0.90,%s::jsonb)
                     RETURNING id"""),
                _tid(request), desc, amount,
                body.debit_account, body.credit_account,
                doc_date,
                wb.get("buyer_name") or "",
                f"RS.ge ζεδ. #{wb_ref}",
                lines_json_val,
            )
            if not draft_row:
                return error_response("დრაფტი ვერ შეიქმნა", "DRAFT_ERROR", "insert returned no row")
            draft_id = draft_row["id"]
            # Link draft back to rsge_waybill for status tracking
            try:
                await conn.execute(
                    _q("UPDATE rsge_waybills SET draft_id=%s, draft_status='drafted' "
                       "WHERE id=%s AND tenant_id=%s"),
                    draft_id, waybill_id, _tid(request),
                )
            except Exception:
                pass  # column may not exist on older DB; migration will fix on next restart
        return ok_response(
            f"ბუღალტრული დრაფტი შეიქმნა (ID={draft_id})",
            {"draft_id": draft_id, "amount": amount,
             "debit_account": body.debit_account,
             "credit_account": body.credit_account,
             "description": desc},
        )
    except Exception as exc:
        log.warning("[RS.GE] create-draft failed wb_id=%s: %s", waybill_id, exc)
        return error_response("დრაფტი ვერ შეიქმნა", "DRAFT_ERROR", str(exc)[:200])


@router.patch("/waybills/{waybill_id}/edit-meta")
async def edit_waybill_meta(waybill_id: int, body: WaybillMetaUpdate, request: Request):
    """Update locally stored waybill metadata: date, amount, goods list."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn, _q
    import json as _json
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(
                _q("SELECT raw_payload FROM rsge_waybills WHERE id = %s AND tenant_id = %s"),
                waybill_id, _tid(request),
            )
            if not row:
                return error_response("ზედნადები ვ. მ.", "NOT_FOUND", f"id={waybill_id}")
            raw_p = _json.loads(row["raw_payload"] or "{}")
            if body.goods_list is not None:
                raw_p["goods_list"] = body.goods_list
            params: list = [_tid(request), waybill_id, _json.dumps(raw_p)]
            set_parts = ["raw_payload = $3::jsonb"]
            if body.begin_date is not None:
                params.append(body.begin_date or None)
                set_parts.append(f"begin_date = ${len(params)}::timestamptz")
            if body.full_amount is not None:
                params.append(body.full_amount)
                set_parts.append(f"full_amount = ${len(params)}")
            await conn.execute(
                f"UPDATE rsge_waybills SET {', '.join(set_parts)} WHERE tenant_id = $1 AND id = $2",
                *params,
            )
        return ok_response("განახლდა", {"id": waybill_id})
    except Exception as exc:
        log.warning("[RS.GE] edit-meta wb_id=%s: %s", waybill_id, exc)
        return error_response("განახლება ვ. მ.", "UPDATE_ERROR", str(exc)[:200])


@router.get("/waybills/goods-by-number")
async def get_waybill_goods_by_number(waybill_number: str, request: Request):
    """Look up synced waybill by waybill_number and return goods from raw_payload."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    import json as _json
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("SELECT id, waybill_number, rsge_id, full_amount, seller_name, seller_tin, "
               "buyer_name, buyer_tin, begin_date, raw_payload "
               "FROM rsge_waybills WHERE tenant_id=%s AND waybill_number=%s "
               "ORDER BY id DESC LIMIT 1"),
            _tid(request), waybill_number.strip(),
        )
    if not row:
        return ok_response("ζεδ. DB-ში ვ.მ.", {"goods": [], "waybill_number": waybill_number})
    wb = dict(row)
    goods = []
    try:
        raw = _json.loads(wb.get("raw_payload") or "{}")
        goods = raw.get("goods_list") or raw.get("GOODS_LIST") or []
    except Exception:
        pass
    return ok_response("საქ. DB-დ.", {
        "local_id": wb["id"],
        "waybill_number": wb.get("waybill_number") or "",
        "full_amount": float(wb.get("full_amount") or 0),
        "seller_name": wb.get("seller_name") or "",
        "buyer_name": wb.get("buyer_name") or "",
        "goods": goods,
    })


@router.get("/waybills/{waybill_id}/goods")
async def get_waybill_goods(waybill_id: int, request: Request):
    """Return goods list for a synced waybill — reads from raw_payload in DB, falls back to SOAP."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    import json as _json
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("SELECT id, waybill_number, rsge_id, full_amount, seller_name, seller_tin, "
               "buyer_name, buyer_tin, begin_date, raw_payload "
               "FROM rsge_waybills WHERE id=%s AND tenant_id=%s"),
            waybill_id, _tid(request),
        )
    if not row:
        return error_response("ζεδ. ვ.მ.", "NOT_FOUND", f"id={waybill_id}")
    wb = dict(row)
    goods = []
    try:
        raw = _json.loads(wb.get("raw_payload") or "{}")
        goods = raw.get("goods_list") or raw.get("GOODS_LIST") or []
    except Exception:
        pass
    # If no goods in DB, try SOAP
    if not goods:
        num = wb.get("waybill_number") or wb.get("rsge_id") or ""
        if num:
            connector = await _connector_async(request)
            live = connector.get_waybill_by_number(num)
            if not live.get("error"):
                goods = live.get("goods_list") or []
    return ok_response("საქ.", {
        "waybill_id": waybill_id,
        "waybill_number": wb.get("waybill_number") or "",
        "full_amount": float(wb.get("full_amount") or 0),
        "seller_name": wb.get("seller_name") or "",
        "buyer_name": wb.get("buyer_name") or "",
        "goods": goods,
    })


@router.get("/waybills/{waybill_id}/linked-invoice")
async def get_linked_invoice(waybill_id: int, request: Request):
    """Find RS.ge invoice(s) linked to a synced waybill (by waybill_number / OVERHEAD_NO).

    First checks local rsge_documents for already-synced invoices.
    Also does a live RS.ge search and returns unsynced matches.
    Returns:
      - local_invoices: already in DB, linked by waybill_number
      - rsge_invoices: from live RS.ge search by OVERHEAD_NO
      - diff: lines on invoice but not on waybill (additional services)
    """
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    from app.api.services.rsge_document_service import find_by_waybill_number
    import json as _json

    try:
        async with get_conn() as conn:
            # 1. Get the waybill record
            wb_row = await conn.fetchrow(
                _q("SELECT id, waybill_number, rsge_id, full_amount, buyer_name, buyer_tin, "
                   "seller_name, seller_tin, begin_date, raw_payload "
                   "FROM rsge_waybills WHERE id=%s AND tenant_id=%s"),
                waybill_id, _tid(request),
            )
            if not wb_row:
                return error_response("ზედნადები ვერ მოიძებნა", "NOT_FOUND", f"id={waybill_id}")

            wb = dict(wb_row)
            wb_num = wb.get("waybill_number") or wb.get("rsge_id") or ""

            # Parse goods from raw_payload
            try:
                raw_payload = _json.loads(wb.get("raw_payload") or "{}")
                wb_goods = raw_payload.get("goods_list") or []
            except Exception:
                wb_goods = []

            # 2. Local invoices already linked
            local_invoices = await find_by_waybill_number(conn, _tid(request), wb_num)

        # 3. Live RS.ge search for invoices by waybill number
        connector = await _connector_async(request)
        rsge_invoices_raw = connector.get_user_invoices(limit=200)
        rsge_matched = [
            inv for inv in rsge_invoices_raw
            if (inv.get("OVERHEAD_NO") or inv.get("overhead_no") or "").strip() == wb_num.strip()
        ]

        # 4. For each matched invoice, try to get full detail with lines
        inv_details = []
        for inv in rsge_matched[:3]:  # limit to 3 to avoid timeout
            inv_id = inv.get("ID") or inv.get("id") or ""
            if not inv_id:
                continue
            detail = connector.get_invoice_by_id(str(inv_id))
            inv_details.append({
                "rsge_id":        inv_id,
                "invoice_number": inv.get("INVOICE_NUMBER") or inv.get("invoice_number") or "",
                "total":          float(inv.get("TOTAL") or 0),
                "vat":            float(inv.get("VAT") or 0),
                "operation_date": inv.get("OPERATION_DATE") or "",
                "status":         inv.get("STATUS") or "",
                "overhead_no":    inv.get("OVERHEAD_NO") or "",
                "lines":          detail.get("lines") or [],
                "error":          detail.get("error"),
            })

        # 5. Compute diff — invoice lines not matched to waybill goods
        wb_names = {(g.get("name") or "").strip().lower() for g in wb_goods}
        diff_lines = []
        for inv in inv_details:
            for line in inv.get("lines") or []:
                lname = (line.get("name") or "").strip().lower()
                if lname and lname not in wb_names:
                    diff_lines.append({**line, "_invoice_id": inv["rsge_id"],
                                       "_invoice_number": inv["invoice_number"]})

        # 6. Combined amount
        wb_total = float(wb.get("full_amount") or 0)
        inv_total = sum(float(i.get("total") or 0) for i in inv_details) or wb_total
        combined = wb_total + sum(float(d.get("amount") or 0) for d in diff_lines)

        return ok_response("ζεδ. ფ-ების შ.", {
            "waybill": {
                "id": waybill_id,
                "waybill_number": wb_num,
                "full_amount": wb_total,
                "buyer_name": wb.get("buyer_name") or "",
                "goods_count": len(wb_goods),
                "goods": wb_goods,
            },
            "local_invoices": [
                {"local_id": r["id"], "rsge_id": r["rsge_id"],
                 "reg_no": r["reg_no"], "amount": float(r["amount"] or 0),
                 "doc_date": str(r["doc_date"] or ""), "status": r["rsge_status"]}
                for r in local_invoices
            ],
            "rsge_invoices": inv_details,
            "diff_lines": diff_lines,
            "summary": {
                "waybill_total": wb_total,
                "invoice_total": inv_total,
                "extra_services_total": sum(float(d.get("amount") or 0) for d in diff_lines),
                "combined_total": combined,
                "has_invoice": len(rsge_matched) > 0,
                "invoice_count": len(rsge_matched),
            },
        })
    except Exception as exc:
        log.warning("[RS.GE] linked-invoice failed wb=%s: %s", waybill_id, exc)
        return error_response("ფ. ძ. ვ.", "LINK_ERROR", str(exc)[:200])


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
            connector=await _connector_async(request), doc_type="waybill",
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
            connector=await _connector_async(request), doc_type="waybill",
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
    result = await _connector_async(request).preview(draft)
    if result["valid"]:
        return ok_response("ზედნადები მზადაა გასაგზავნად", result)
    return error_response("ზედნადებში შეცდომებია", "VALIDATION_FAILED", result)


@router.post("/waybill")
async def submit_waybill(body: WaybillSubmitRequest, request: Request):
    """Create and submit a new waybill to RS.ge."""
    require_permission(request, "posting:write")
    require_test_mode("submit_waybill")
    conn_r = await _connector_async(request)
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
    conn_r = await _connector_async(request)
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
    conn_r = await _connector_async(request)
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
    result = await _connector_async(request).verify_taxpayer(inn)
    if result.get("valid"):
        return ok_response("გადასახადის გადამხდელი ვალიდურია", result)
    return ok_response("გადასახადის გადამხდელი არ მოიძებნა", result)


@router.post("/taxpayer/verify")
async def verify_taxpayer_post(body: TaxpayerRequest, request: Request):
    """Verify taxpayer INN (POST form)."""
    require_permission(request, "posting:read")
    result = await _connector_async(request).verify_taxpayer(body.inn)
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
                       {"types": (await _connector_async(request)).get_waybill_types()})


@router.get("/units")
async def rs_ge_units(request: Request):
    require_permission(request, "posting:read")
    return ok_response("საზომი ერთეულები",
                       {"units": (await _connector_async(request)).get_waybill_units()})


# ── Partner mapping ──────────────────────────────────────────────────────────

@router.get("/partner-map")
async def list_partner_map(request: Request):
    """Return all partner TIN→account mappings for this tenant."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("SELECT id, tin, partner_name, account_code, notes, created_at "
               "FROM rsge_partner_map WHERE tenant_id = %s ORDER BY partner_name"),
            _tid(request),
        )
    return ok_response("partner map", [dict(r) for r in rows])


@router.post("/partner-map")
async def upsert_partner_map(body: PartnerMapRequest, request: Request):
    """Create or update a partner TIN→credit account mapping."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""INSERT INTO rsge_partner_map (tenant_id, tin, partner_name, account_code, notes)
                  VALUES (%s,%s,%s,%s,%s)
                  ON CONFLICT (tenant_id, tin) DO UPDATE
                    SET partner_name=EXCLUDED.partner_name,
                        account_code=EXCLUDED.account_code,
                        notes=EXCLUDED.notes
                  RETURNING id"""),
            _tid(request), body.tin.strip(), body.partner_name, body.account_code.strip(), body.notes,
        )
    return ok_response("შენახულია", {"id": row["id"]})


@router.delete("/partner-map/{map_id}")
async def delete_partner_map(map_id: int, request: Request):
    require_permission(request, "posting:write")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        await conn.execute(
            _q("DELETE FROM rsge_partner_map WHERE id = %s AND tenant_id = %s"),
            map_id, _tid(request),
        )
    return ok_response("წაიშალა", {"id": map_id})


# ── Item mapping ─────────────────────────────────────────────────────────────

@router.get("/item-map")
async def list_item_map(request: Request):
    """Return all item code→account mappings for this tenant."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("SELECT id, item_code, item_name, account_code, vat_exempt, created_at "
               "FROM rsge_item_map WHERE tenant_id = %s ORDER BY item_name"),
            _tid(request),
        )
    return ok_response("item map", [dict(r) for r in rows])


@router.post("/item-map")
async def upsert_item_map(body: ItemMapRequest, request: Request):
    """Create or update an item code→debit account mapping."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""INSERT INTO rsge_item_map (tenant_id, item_code, item_name, account_code, vat_exempt)
                  VALUES (%s,%s,%s,%s,%s)
                  ON CONFLICT (tenant_id, item_code) DO UPDATE
                    SET item_name=EXCLUDED.item_name,
                        account_code=EXCLUDED.account_code,
                        vat_exempt=EXCLUDED.vat_exempt
                  RETURNING id"""),
            _tid(request), body.item_code.strip(), body.item_name, body.account_code.strip(), body.vat_exempt,
        )
    return ok_response("შენახულია", {"id": row["id"]})


@router.delete("/item-map/{map_id}")
async def delete_item_map(map_id: int, request: Request):
    require_permission(request, "posting:write")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        await conn.execute(
            _q("DELETE FROM rsge_item_map WHERE id = %s AND tenant_id = %s"),
            map_id, _tid(request),
        )
    return ok_response("წაიშალა", {"id": map_id})


# ── Auto-suggest draft accounts ───────────────────────────────────────────────

@router.post("/suggest-draft")
async def suggest_draft_accounts(body: SuggestDraftRequest, request: Request):
    """Suggest Dr/Cr accounts for a waybill based on partner and item mappings."""
    require_permission(request, "posting:read")
    import json as _json
    from app.api.db import get_conn, _q
    result: dict = {
        "credit_account": None,
        "debit_account":  None,
        "vat_exempt":     False,
        "source":         "default",
    }
    try:
        async with get_conn() as conn:
            # 1. Partner TIN → credit account
            if body.seller_tin:
                pm = await conn.fetchrow(
                    _q("SELECT account_code, partner_name FROM rsge_partner_map "
                       "WHERE tenant_id = %s AND tin = %s"),
                    _tid(request), body.seller_tin.strip(),
                )
                if pm:
                    result["credit_account"] = pm["account_code"]
                    result["partner_name"] = pm["partner_name"]
                    result["source"] = "partner_map"

            # 2. Item codes → debit account (first match wins)
            goods = body.goods_list or []
            codes = [
                str(g.get("bar_code") or g.get("product_code") or g.get("code") or "").strip()
                for g in goods
            ]
            codes = [c for c in codes if c]
            if codes:
                for code in codes:
                    im = await conn.fetchrow(
                        _q("SELECT account_code, vat_exempt FROM rsge_item_map "
                           "WHERE tenant_id = %s AND item_code = %s"),
                        _tid(request), code,
                    )
                    if im:
                        result["debit_account"] = im["account_code"]
                        result["vat_exempt"] = bool(im["vat_exempt"])
                        if result["source"] == "default":
                            result["source"] = "item_map"
                        else:
                            result["source"] = "both_maps"
                        break
    except Exception as exc:
        log.debug("[RS.GE] suggest-draft error: %s", exc)

    return ok_response("შეთ.", result)


# ── Own TIN (auto-detect purchase vs sales direction) ─────────────────────────

class OwnTinRequest(BaseModel):
    tin: str = Field(..., min_length=5, max_length=20, description="Company own TIN (საიდ. კოდი)")


@router.get("/own-tin")
async def get_own_tin(request: Request):
    """Return the tenant's own TIN stored in settings."""
    require_permission(request, "posting:read")
    from app.api.services.tenant_config_service import get_tenant_setting
    tin = await get_tenant_setting(_tid(request), "rsge.own_tin", "")
    return ok_response("own TIN", {"own_tin": tin or "", "set": bool(tin)})


@router.post("/own-tin")
async def set_own_tin(body: OwnTinRequest, request: Request):
    """Store the tenant's own TIN — used to auto-detect Dr/Cr direction on invoices."""
    require_permission(request, "posting:write")
    from app.api.services.tenant_config_service import set_tenant_setting
    ok = await set_tenant_setting(_tid(request), "rsge.own_tin", body.tin.strip())
    if ok:
        return ok_response("TIN შენახულია", {"own_tin": body.tin.strip()})
    return error_response("TIN ვ. შ.", "SETTING_ERROR", "")


# ── Comparison results ────────────────────────────────────────────────────────

class ComparisonSaveRequest(BaseModel):
    waybill_id:  Optional[int] = None
    document_id: Optional[int] = None
    status:      str = Field("pending", description="matched|partial|mismatch|pending")
    wb_amount:   float = 0.0
    inv_amount:  float = 0.0
    diff_lines:  Optional[List[Dict[str, Any]]] = None
    notes:       Optional[str] = None


@router.post("/comparison-results")
async def save_comparison_result(body: ComparisonSaveRequest, request: Request):
    """Persist a waybill↔invoice comparison result for audit trail."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn, _q
    import json as _json
    diff_amt = round(abs((body.wb_amount or 0) - (body.inv_amount or 0)), 4)
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""INSERT INTO rsge_comparison_results
                   (tenant_id, waybill_id, document_id, status,
                    wb_amount, inv_amount, diff_amount, diff_lines,
                    notes, reviewed_by)
                 VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
                 RETURNING id, created_at"""),
            _tid(request),
            body.waybill_id, body.document_id, body.status,
            body.wb_amount, body.inv_amount, diff_amt,
            _json.dumps(body.diff_lines or []),
            body.notes, _actor(request),
        )
    return ok_response("შედ. შ.", {
        "id": row["id"],
        "diff_amount": diff_amt,
        "status": body.status,
        "created_at": str(row["created_at"]),
    })


# ── Document comparison endpoints ────────────────────────────────────────────

@router.get("/documents/{doc_id}/compare")
async def compare_document(doc_id: int, request: Request,
                            target: str = "evidence", own_inn: str = ""):
    """Compare a synced RS.ge document vs evidence / draft / posted ledger.

    target: evidence | journal_draft | posted_ledger
    """
    require_permission(request, "posting:read")
    from app.api.db import get_conn
    from app.api.services.rsge_comparison_service import (
        compare_document_vs_evidence,
        compare_document_vs_draft,
        compare_document_vs_ledger,
    )
    tid = _tid(request)
    effective_inn = own_inn.strip()
    if not effective_inn:
        from app.api.services.tenant_config_service import get_tenant_setting
        effective_inn = await get_tenant_setting(tid, "rsge.own_tin", "") or ""
    async with get_conn() as conn:
        if target == "journal_draft":
            result = await compare_document_vs_draft(conn, tid, doc_id, effective_inn)
        elif target == "posted_ledger":
            result = await compare_document_vs_ledger(conn, tid, doc_id)
        else:
            result = await compare_document_vs_evidence(conn, tid, doc_id, effective_inn)
    return ok_response(f"შ. ({result.get('comparison_status')})", result)


@router.post("/documents/{doc_id}/compare-and-store")
async def compare_and_store_document(doc_id: int, request: Request,
                                      target: str = "evidence"):
    """Compare and persist result to rsge_comparison_results."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_comparison_service import (
        compare_document_vs_evidence,
        compare_document_vs_draft,
        compare_document_vs_ledger,
        save_comparison_result,
    )
    tid = _tid(request)
    from app.api.services.tenant_config_service import get_tenant_setting
    own_inn = await get_tenant_setting(tid, "rsge.own_tin", "") or ""
    async with get_conn() as conn:
        if target == "journal_draft":
            result = await compare_document_vs_draft(conn, tid, doc_id, own_inn)
        elif target == "posted_ledger":
            result = await compare_document_vs_ledger(conn, tid, doc_id)
        else:
            result = await compare_document_vs_evidence(conn, tid, doc_id, own_inn)
        result_id = await save_comparison_result(conn, tid, result, _actor(request))
    return ok_response(f"შ. შ. (id={result_id})", {**result, "comparison_result_id": result_id})


@router.get("/waybills/{waybill_id}/compare")
async def compare_waybill(waybill_id: int, request: Request):
    """Compare a synced waybill against its linked invoice."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn
    from app.api.services.rsge_comparison_service import compare_waybill_vs_invoice
    async with get_conn() as conn:
        result = await compare_waybill_vs_invoice(conn, _tid(request), waybill_id)
    return ok_response(f"ζεδ. შ. ({result.get('comparison_status')})", result)


@router.post("/waybills/{waybill_id}/compare-and-store")
async def compare_and_store_waybill(waybill_id: int, request: Request):
    """Compare waybill vs invoice and persist result."""
    require_permission(request, "posting:write")
    from app.api.db import get_conn
    from app.api.services.rsge_comparison_service import (
        compare_waybill_vs_invoice, save_comparison_result,
    )
    async with get_conn() as conn:
        result = await compare_waybill_vs_invoice(conn, _tid(request), waybill_id)
        result_id = await save_comparison_result(conn, _tid(request), result, _actor(request))
    return ok_response(f"ζεδ. შ. შ. (id={result_id})", {**result, "comparison_result_id": result_id})


@router.get("/comparison-results")
async def list_comparison_results(request: Request, waybill_id: Optional[int] = None,
                                  limit: int = 50):
    """List comparison results, optionally filtered by waybill."""
    require_permission(request, "posting:read")
    from app.api.db import get_conn, _q
    async with get_conn() as conn:
        if waybill_id:
            rows = await conn.fetch(
                _q("SELECT id, waybill_id, document_id, status, wb_amount, inv_amount, "
                   "diff_amount, notes, reviewed_by, created_at "
                   "FROM rsge_comparison_results WHERE tenant_id=%s AND waybill_id=%s "
                   "ORDER BY id DESC LIMIT %s"),
                _tid(request), waybill_id, limit,
            )
        else:
            rows = await conn.fetch(
                _q("SELECT id, waybill_id, document_id, status, wb_amount, inv_amount, "
                   "diff_amount, notes, reviewed_by, created_at "
                   "FROM rsge_comparison_results WHERE tenant_id=%s "
                   "ORDER BY id DESC LIMIT %s"),
                _tid(request), limit,
            )
    return ok_response(f"შედ. ({len(rows)})", [dict(r) for r in rows])
