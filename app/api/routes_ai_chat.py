"""
Bridge Hub — AI Chat Routes
→ app/api/routes_ai_chat.py
Thin routes only
"""

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from app.api.authz import require_permission, require_signed_tenant_permission
from app.api.services.ai_session_scope import scoped_ai_session
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.services.ai_chat_service import (
    handle_ai_chat,
    get_ai_system_stats,
    run_ai_search,
    run_vat_calc,
    run_dividend_calc,
    run_payroll_calc,
    run_cit_calc,
    run_depreciation_calc,
    run_classify_tx,
    run_learn_rule,
    run_index_files,
    run_vector_stats,
)

router = APIRouter(prefix="/api/ai", tags=["AI Assistant"])


# ─────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    tenant_id: Optional[str] = "global"
    use_vector_search: Optional[bool] = True
    role: Optional[str] = None  # "accountant" | "consultant" | "assistant"


class SuggestedAction(BaseModel):
    action: str
    label: str
    route: str
    method: Optional[str] = "POST"
    params: Optional[dict] = None


class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
    confidence: float = 0.0
    search_method: str = "keyword"
    session_id: Optional[str] = None
    suggested_actions: List[SuggestedAction] = []


class VATRequest(BaseModel):
    amount: float
    inclusive: bool = True
    service_type: Optional[str] = "standard"
    payment_status: Optional[str] = "paid"


class PayrollRequest(BaseModel):
    gross: float
    include_employee_payg: Optional[bool] = True
    mode: Optional[str] = "gross"


class CITRequest(BaseModel):
    distributed_profit: float


class DividendRequest(BaseModel):
    gross_amount: float
    cit_rate: Optional[float] = 0.15


class DepreciationRequest(BaseModel):
    cost: float
    residual: float
    useful_life_years: int
    method: Optional[str] = "straight_line"


class ClassifyRequest(BaseModel):
    description: str
    tenant_id: Optional[str] = "global"


class LearnRequest(BaseModel):
    pattern: str
    account: str
    tenant_id: Optional[str] = "global"
    note: Optional[str] = ""
    use_vector: Optional[bool] = True


class IndexRequest(BaseModel):
    files_dir: Optional[str] = None
    force_reindex: Optional[bool] = False


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────
@router.get("/stats")
async def ai_stats(request: Request):
    require_signed_tenant_permission(request, "chat:use")
    # Global learned-rule/vector counts are not tenant-isolated.
    from app.api.services import ai_calculators_service as calc
    return {
        "kb_loaded": bool(calc.KB_LOADED),
        "accounting_rules_loaded": bool(calc.ACCT_RULES_LOADED),
        "vector_search_tenant_isolated": False,
    }


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    request: Request,
    message: str = Form(""),
    session_id: str = Form(None),
    tenant_id: str = Form("global"),
    use_vector_search: bool = Form(True),
    role: str = Form(None),
    draft_id: Optional[int] = Form(None),
    file: UploadFile = File(None),
    files: Optional[List[UploadFile]] = File(None),
):
    # Never use caller-submitted tenant or role as an authorization claim.
    tenant_id, scoped_session_id = scoped_ai_session(request, session_id)
    message = (message or "").strip()

    # Merge: multi-file field + legacy single file field
    all_files: List[UploadFile] = []
    if files:
        all_files = [f for f in files if f and f.filename]
    if file and file.filename and file not in all_files:
        all_files.append(file)

    if not message and not all_files:
        raise HTTPException(status_code=400, detail="შეტყობინება ან ფაილი აუცილებელია")
    # AI processing can create drafts via files or posting intent.
    # chat:use alone never authorizes a financial write.
    if all_files or "გატარე" in message.lower() or "post" in message.lower():
        require_signed_tenant_permission(request, "posting:write")

    result = await handle_ai_chat(
        message=message,
        session_id=scoped_session_id,
        tenant_id=tenant_id,
        # Shared Chroma collections are not tenant isolated.
        use_vector_search=False,
        file=all_files[0] if len(all_files) == 1 else None,
        files=all_files if len(all_files) > 1 else None,
        role=getattr(request.state, "role", None),
        draft_id=draft_id,
    )

    # The scoped DB/LLM identifier is internal. Clients keep their original
    # public session ID; otherwise they would double-scope it on the next turn.
    payload = ChatResponse(**{**result, "session_id": session_id})
    return JSONResponse(
        content=jsonable_encoder(payload),
        media_type="application/json; charset=utf-8",
    )


@router.post("/action/preview")
async def preview_action(request: Request, body: dict):
    """
    PREVIEW a suggested_action — returns what WOULD happen, never executes.
    This is the primary endpoint for suggested_actions from /api/ai/chat.

    Body: { "action": "approve_draft", "params": {"draft_id": 1130} }
    Response: { "preview": {...}, "requires_human_approval": true, "action": "..." }
    """
    tenant_id = require_signed_tenant_permission(request, "chat:use")
    from app.api.response_utils import ok_response
    action = body.get("action", "")
    params = body.get("params") or {}

    _NAVIGATION_ACTIONS = {
        "view_report":  {"url": "/reports",  "label": "Reports გვერდი"},
        "view_audit":   {"url": "/audit",    "label": "Audit Log გვერდი"},
        "open_payroll": {"url": "/payroll",  "label": "Payroll გვერდი"},
        "view_draft":   {"url": "/static/approval.html", "label": "Approval გვერდი"},
    }

    if action in _NAVIGATION_ACTIONS:
        nav = _NAVIGATION_ACTIONS[action]
        return ok_response("Navigation preview", {
            "action": action,
            "url": nav["url"],
            "label": nav["label"],
            "requires_human_approval": False,
            "preview": f"გახსნის: {nav['label']}",
        })

    if action == "approve_draft":
        require_signed_tenant_permission(request, "approval:read")
        draft_id = params.get("draft_id")
        if not draft_id:
            raise HTTPException(400, "draft_id required")
        from app.api.db import get_conn as _get_conn, _q
        async with _get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT id, description, amount, partner, status, confidence "
                "FROM journal_drafts WHERE id=%s AND tenant_id=%s"
            ), int(draft_id), tenant_id)
        if not row:
            raise HTTPException(404, f"Draft #{draft_id} not found")
        d = dict(row)
        return ok_response("Approve preview", {
            "action": "approve_draft",
            "draft_id": draft_id,
            "requires_human_approval": True,
            "confirm_url": f"/api/approval/approve/{draft_id}",
            "confirm_method": "POST",
            "preview": {
                "description": d["description"],
                "amount": float(d["amount"] or 0),
                "partner": d["partner"],
                "current_status": d["status"],
                "new_status": "approved",
                "confidence": float(d["confidence"] or 0),
            },
            "warning": "ეს მოქმედება draft-ს დაამტკიცებს. დასადასტურებლად გამოიძახეთ confirm_url.",
        })

    if action == "reject_draft":
        require_signed_tenant_permission(request, "approval:read")
        draft_id = params.get("draft_id")
        reason = params.get("reason", "")
        if not draft_id:
            raise HTTPException(400, "draft_id required")
        from app.api.db import get_conn as _get_conn, _q
        async with _get_conn() as conn:
            row = await conn.fetchrow(_q(
                "SELECT id, description, amount, partner, status "
                "FROM journal_drafts WHERE id=%s AND tenant_id=%s"
            ), int(draft_id), tenant_id)
        if not row:
            raise HTTPException(404, f"Draft #{draft_id} not found")
        d = dict(row)
        return ok_response("Reject preview", {
            "action": "reject_draft",
            "draft_id": draft_id,
            "requires_human_approval": True,
            "confirm_url": f"/api/approval/reject/{draft_id}",
            "confirm_method": "POST",
            "preview": {
                "description": d["description"],
                "amount": float(d["amount"] or 0),
                "partner": d["partner"],
                "current_status": d["status"],
                "new_status": "rejected",
                "reason": reason,
            },
            "warning": "ეს მოქმედება draft-ს უარყოფს. დასადასტურებლად გამოიძახეთ confirm_url.",
        })

    if action in ("export_1c", "post_balance_ge", "create_invoice", "sync_bank"):
        _labels = {
            "export_1c":       "1C Export",
            "post_balance_ge": "Balance.ge Posting",
            "create_invoice":  "Invoice შექმნა",
            "sync_bank":       "Bank Sync",
        }
        return ok_response(f"{action} preview", {
            "action": action,
            "requires_human_approval": True,
            "params": params,
            "preview": f"{_labels.get(action, action)} — ადამიანის დადასტურება საჭიროა",
            "warning": "ეს მოქმედება გარე სისტემაზე მოქმედებს. AI ვერ შეასრულებს — ადამიანი უნდა დაადასტუროს.",
        })

    raise HTTPException(400, f"Unknown action: {action}")


@router.post("/action/confirm")
async def confirm_action(request: Request, body: dict):
    """
    CONFIRM and EXECUTE a previously previewed action.
    Human explicitly calls this after reviewing the preview.

    Body: { "action": "approve_draft", "params": {"draft_id": 1130} }
    """
    # P0: approve/reject requires approval:write, not just chat:use
    require_permission(request, "approval:write")
    tenant_id = require_signed_tenant_permission(request, "approval:write")
    action = body.get("action", "")
    params = body.get("params") or {}

    if action == "approve_draft":
        draft_id = params.get("draft_id")
        if not draft_id:
            raise HTTPException(400, "draft_id required")
        from app.api.services.approval_service import approve_draft_service
        return await approve_draft_service(int(draft_id), tenant_id=tenant_id)

    if action == "reject_draft":
        draft_id = params.get("draft_id")
        reason = params.get("reason", "human confirmed via chat")
        if not draft_id:
            raise HTTPException(400, "draft_id required")
        from app.api.services.approval_service import reject_draft_service
        return await reject_draft_service(int(draft_id), reason, tenant_id=tenant_id)

    raise HTTPException(400, f"Action '{action}' cannot be confirmed via chat. Use the dedicated module.")


# ─── Session management ──────────────────────────────────────────────────────

@router.get("/session/{session_id}")
async def get_session(session_id: str, request: Request):
    """Return metadata about a chat session."""
    tenant_id, scoped_id = scoped_ai_session(request, session_id)
    from app.api.services.chat_session_service import get_session_summary
    from app.api.response_utils import ok_response
    summary = await get_session_summary(scoped_id, tenant_id)
    if summary.get("exists"):
        summary["session_id"] = session_id
    return ok_response("Session", summary)


@router.delete("/session/{session_id}")
async def clear_session(session_id: str, request: Request):
    """Clear conversation history for a session (fresh start)."""
    tenant_id, scoped_id = scoped_ai_session(request, session_id)
    from app.api.services.chat_session_service import clear_history
    from app.api.services.llm_service import _chat_history
    from app.api.response_utils import ok_response
    await clear_history(scoped_id, tenant_id)
    _chat_history.pop((tenant_id, scoped_id), None)
    return ok_response("Session cleared", {"session_id": session_id})


@router.get("/search")
async def ai_search(request: Request, q: str, top_k: int = 5, use_vector: bool = True):
    require_signed_tenant_permission(request, "chat:use")
    result = run_ai_search(q=q, top_k=max(1, min(top_k, 20)), use_vector=False)
    return {**result, "vector_search_tenant_isolated": False}


@router.post("/vat")
async def vat_calc(body: VATRequest, request: Request):
    require_signed_tenant_permission(request, "chat:use")
    return run_vat_calc(body)


@router.post("/dividend")
async def dividend_calc(body: DividendRequest, request: Request):
    require_signed_tenant_permission(request, "chat:use")
    return run_dividend_calc(body)


@router.post("/payroll")
async def payroll_calc(body: PayrollRequest, request: Request):
    require_signed_tenant_permission(request, "chat:use")
    return run_payroll_calc(body)


@router.post("/cit")
async def cit_calc(body: CITRequest, request: Request):
    require_signed_tenant_permission(request, "chat:use")
    return run_cit_calc(body)


@router.post("/depreciation")
async def dep_calc(body: DepreciationRequest, request: Request):
    require_signed_tenant_permission(request, "chat:use")
    return run_depreciation_calc(body)


@router.post("/classify")
async def classify_tx(body: ClassifyRequest, request: Request):
    tenant_id = require_signed_tenant_permission(request, "chat:use")
    return run_classify_tx(body.model_copy(update={"tenant_id": tenant_id}))


@router.post("/learn")
async def learn_rule(body: LearnRequest, request: Request):
    tenant_id = require_signed_tenant_permission(request, "patterns:manage")
    # Global Chroma learned-rule collection is not tenant-filtered on reads.
    return await run_learn_rule(body.model_copy(update={
        "tenant_id": tenant_id, "use_vector": False,
    }))


@router.post("/index")
async def index_files_ep(body: IndexRequest, request: Request):
    require_signed_tenant_permission(request, "patterns:manage")
    # Remote directory scanning / global vector writes are not tenant-safe;
    # keep all previously indexed files intact, require separate offline review.
    raise HTTPException(status_code=503, detail="Remote AI file indexing disabled")


@router.get("/vector-stats")
async def vector_stats(request: Request):
    require_signed_tenant_permission(request, "patterns:manage")
    raise HTTPException(status_code=503, detail="Tenant-scoped vector stats unavailable")


# ─── Export endpoints ────────────────────────────────────────────────────────

@router.get("/export/txt")
async def export_chat_txt(session_id: str, request: Request):
    """Export full conversation history as plain text."""
    tenant_id, scoped_id = scoped_ai_session(request, session_id)
    from fastapi.responses import PlainTextResponse
    from app.api.services.chat_session_service import load_history

    messages = await load_history(scoped_id, tenant_id)

    if not messages:
        raise HTTPException(status_code=404, detail="Session not found or empty")

    lines = [f"Bridge Hub Chat Export — session: {session_id}\n"]
    for msg in messages:
        role = msg.get("role", "?").upper()
        content = msg.get("content", "")
        lines.append(f"[{role}]\n{content}\n")

    return PlainTextResponse(
        content="\n".join(lines),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="chat_{session_id}.txt"'},
    )


@router.get("/export/md")
async def export_chat_md(session_id: str, request: Request):
    """Export full conversation history as Markdown."""
    tenant_id, scoped_id = scoped_ai_session(request, session_id)
    from fastapi.responses import PlainTextResponse
    from app.api.services.chat_session_service import load_history

    messages = await load_history(scoped_id, tenant_id)

    if not messages:
        raise HTTPException(status_code=404, detail="Session not found or empty")

    lines = [f"# Bridge Hub Chat — `{session_id}`\n"]
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        icon = "🧑" if role == "user" else "🤖"
        lines.append(f"## {icon} {role.capitalize()}\n\n{content}\n")

    return PlainTextResponse(
        content="\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="chat_{session_id}.md"'},
    )