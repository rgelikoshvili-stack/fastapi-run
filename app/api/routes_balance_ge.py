from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from typing import List
import httpx
from app.api.authz import require_permission
from app.api.response_utils import ok_response, error_response, http_error
from app.api.db import get_conn, _q
from app.api.tenant_context import resolve_tenant_id
from app.api.services.balance_credentials_service import get_balance_credentials
from app.ai_systems.external_api_ai import assess_human_gate

router = APIRouter(prefix="/balance-ge", tags=["balance-ge"])

BALANCE_GE_URL = "https://api.balance.ge/v1"

class JournalPostRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_ids: List[int]

@router.post("/test-connection")
async def test_connection(request: Request):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        creds = await get_balance_credentials(tenant_id)
    except RuntimeError:
        return http_error(503, "Balance.ge credentials unavailable")
    if not creds.get("api_key"):
        return http_error(503, "Balance.ge credentials unavailable")
    company_id = creds.get("company_id") or "default"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BALANCE_GE_URL}/company/{company_id}",
                headers={"Authorization": f"Bearer {creds['api_key']}"}
            )
            if r.status_code == 200:
                return ok_response("Balance.ge connected", {"connected": True})
            else:
                return error_response(
                    "Connection failed",
                    "AUTH_ERROR",
                    f"Status: {r.status_code}"
                )
    except Exception:
        return error_response("Connection error", "CONNECT_ERROR", "")

@router.post("/post-journals")
async def post_journals(req: JournalPostRequest, request: Request):
    require_permission(request, "posting:write")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    try:
        creds = await get_balance_credentials(tenant_id)
    except RuntimeError:
        return http_error(503, "Balance.ge credentials unavailable")
    if not creds.get("api_key"):
        return http_error(503, "Balance.ge credentials unavailable")
    company_id = creds.get("company_id") or "default"
    async with get_conn() as conn:
        drafts = [dict(r) for r in await conn.fetch(_q(
            "SELECT * FROM journal_drafts WHERE id = ANY(%s) AND status='approved' AND tenant_id=%s"),
            req.draft_ids, tenant_id)]

    if not drafts:
        return error_response("No approved drafts found", "NOT_FOUND", "")

    gate_blocks = []
    for d in drafts:
        gate = assess_human_gate(d, "balance")
        if gate["requires_human"]:
            gate_blocks.append({"draft_id": d["id"], "reasons": gate["reasons"], "risk_level": gate["risk_level"]})

    if gate_blocks:
        return error_response(
            "Human approval required before posting",
            "HUMAN_GATE_REQUIRED",
            gate_blocks,
        )

    posted, failed = [], []
    async with httpx.AsyncClient(timeout=30) as client:
        for d in drafts:
            payload = {
                "date": d.get("date"),
                "description": d.get("description"),
                "debit_account": d.get("debit_account"),
                "credit_account": d.get("credit_account"),
                "amount": d.get("amount"),
                "partner": d.get("partner"),
            }
            try:
                r = await client.post(
                    f"{BALANCE_GE_URL}/journal",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {creds['api_key']}",
                        "X-Company-ID": company_id
                    }
                )
                if r.status_code in (200, 201):
                    posted.append({"id": d["id"], "status": "posted"})
                else:
                    failed.append({
                        "id": d["id"],
                        "error": f"Balance.ge returned HTTP {r.status_code}",
                    })
            except Exception:
                failed.append({"id": d["id"], "error": "Balance.ge request failed"})

    return ok_response("Balance.ge posting complete", {
        "posted_count": len(posted),
        "failed_count": len(failed),
        "posted": posted,
        "failed": failed,
        "tenant_id": tenant_id,
    })

@router.get("/export-format/{draft_id}")
async def export_format(draft_id: int, request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        d = await conn.fetchrow(_q(
            "SELECT * FROM journal_drafts WHERE id=%s AND tenant_id=%s"),
            draft_id, tenant_id)

    if not d:
        return error_response("Draft not found", "NOT_FOUND", "")

    d = dict(d)
    balance_ge_format = {
        "TransactionDate": d.get("date"),
        "Description": d.get("description"),
        "DebitAccount": d.get("debit_account"),
        "CreditAccount": d.get("credit_account"),
        "Amount": d.get("amount"),
        "Currency": "GEL",
        "PartnerName": d.get("partner"),
        "DocumentType": "journal",
        "SourceSystem": "BridgeHub",
        "TenantID": tenant_id,
    }
    return ok_response("Balance.ge format", balance_ge_format)
