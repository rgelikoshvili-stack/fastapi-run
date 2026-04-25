"""
Bridge Hub — AI Chat Routes
→ app/api/routes_ai_chat.py
Thin routes only
"""

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
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


class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
    confidence: float = 0.0
    search_method: str = "keyword"
    session_id: Optional[str] = None


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
async def ai_stats():
    return get_ai_system_stats()


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
):
    # Prefer tenant_id from auth middleware over form field
    tenant_id = getattr(request.state, "tenant_id", None) or tenant_id or "global"
    message = (message or "").strip()

    if not message and not file:
        raise HTTPException(status_code=400, detail="შეტყობინება ან ფაილი აუცილებელია")

    result = await handle_ai_chat(
        message=message,
        session_id=session_id,
        tenant_id=tenant_id,
        use_vector_search=use_vector_search,
        file=file,
        role=role or None,
        draft_id=draft_id,
    )

    payload = ChatResponse(**result)
    return JSONResponse(
        content=jsonable_encoder(payload),
        media_type="application/json; charset=utf-8",
    )


@router.get("/search")
async def ai_search(q: str, top_k: int = 5, use_vector: bool = True):
    return run_ai_search(q=q, top_k=top_k, use_vector=use_vector)


@router.post("/vat")
async def vat_calc(request: VATRequest):
    return run_vat_calc(request)


@router.post("/dividend")
async def dividend_calc(request: DividendRequest):
    return run_dividend_calc(request)


@router.post("/payroll")
async def payroll_calc(request: PayrollRequest):
    return run_payroll_calc(request)


@router.post("/cit")
async def cit_calc(request: CITRequest):
    return run_cit_calc(request)


@router.post("/depreciation")
async def dep_calc(request: DepreciationRequest):
    return run_depreciation_calc(request)


@router.post("/classify")
async def classify_tx(request: ClassifyRequest):
    return run_classify_tx(request)


@router.post("/learn")
async def learn_rule(request: LearnRequest):
    return run_learn_rule(request)


@router.post("/index")
async def index_files_ep(request: IndexRequest):
    return run_index_files(request)


@router.get("/vector-stats")
async def vector_stats():
    return run_vector_stats()