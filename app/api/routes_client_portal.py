"""
app/api/routes_client_portal.py
Bridge Hub — Client Portal
კლიენტი ხედავს მხოლოდ საკუთარ ტრანზაქციებს.
Core approval logic არ ეხება.
"""
from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import psycopg2.extras
from app.api.db import get_db
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/client", tags=["client-portal"])


# ========== Models ==========

class ClientUploadRequest(BaseModel):
    description: Optional[str] = None
    partner: Optional[str] = None
    amount: Optional[float] = None


# ========== Client Dashboard ==========

@router.get("/dashboard")
def client_dashboard(request: Request):
    """
    კლიენტის მთავარი გვერდი — საკუთარი ტრანზაქციების შეჯამება.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved,
                COUNT(CASE WHEN status = 'auto_approved' THEN 1 END) as auto_approved,
                COUNT(CASE WHEN status = 'pending_approval' THEN 1 END) as pending,
                COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected,
                COALESCE(SUM(amount), 0) as total_amount
            FROM journal_drafts
            WHERE tenant_id = %s
              AND partner = %s
        """, (tenant_id, client_id))
        stats = dict(cur.fetchone())

        cur.execute("""
            SELECT id, date, description, amount, status, created_at
            FROM journal_drafts
            WHERE tenant_id = %s
              AND partner = %s
            ORDER BY created_at DESC
            LIMIT 10
        """, (tenant_id, client_id))
        recent = [dict(r) for r in cur.fetchall()]

        return {
            "ok": True,
            "client_id": client_id,
            "tenant_id": tenant_id,
            "stats": {
                "total": stats["total"],
                "approved": stats["approved"],
                "auto_approved": stats["auto_approved"],
                "pending": stats["pending"],
                "rejected": stats["rejected"],
                "total_amount": round(float(stats["total_amount"]), 2),
            },
            "recent_transactions": recent,
            "generated_at": datetime.now().isoformat(),
        }
    finally:
        cur.close()
        conn.close()


# ========== Client Transactions ==========

@router.get("/transactions")
def client_transactions(
    request: Request,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    კლიენტის ტრანზაქციების სია.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if status:
            cur.execute("""
                SELECT id, date, description, amount, status,
                       account_code, confidence, created_at, source_type
                FROM journal_drafts
                WHERE tenant_id = %s AND partner = %s AND status = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (tenant_id, client_id, status, limit, offset))
        else:
            cur.execute("""
                SELECT id, date, description, amount, status,
                       account_code, confidence, created_at, source_type
                FROM journal_drafts
                WHERE tenant_id = %s AND partner = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (tenant_id, client_id, limit, offset))

        items = [dict(r) for r in cur.fetchall()]

        return {
            "ok": True,
            "client_id": client_id,
            "tenant_id": tenant_id,
            "count": len(items),
            "limit": limit,
            "offset": offset,
            "transactions": items,
        }
    finally:
        cur.close()
        conn.close()


# ========== Client Upload ==========

@router.post("/upload")
async def client_upload(
    request: Request,
    file: UploadFile = File(...),
):
    """
    კლიენტი ატვირთავს დოკუმენტს.
    OCR → Draft → pending_approval queue-ში.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    if not file.filename:
        raise HTTPException(status_code=400, detail="ფაილი სავალდებულოა")

    allowed = (".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".csv")
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(
            status_code=400,
            detail=f"დასაშვები ფორმატები: {', '.join(allowed)}"
        )

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="ფაილი 10MB-ზე მეტია")

    from app.api.services.ocr_service import extract_invoice_fields, create_draft_from_invoice
    fields = extract_invoice_fields(file.filename, data)

    if fields.get("amount"):
        fields["partner"] = client_id
        draft = create_draft_from_invoice(
            fields,
            tenant_id=tenant_id,
            source_type="client_upload",
        )
    else:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute("""
                INSERT INTO journal_drafts (
                    date, description, partner, amount,
                    debit_account, credit_account, account_code,
                    reason, confidence, status, source_type, tenant_id, created_at
                ) VALUES (
                    NOW()::date, %s, %s, 0,
                    '7100', '1210', '7100',
                    'client_upload', 0.5, 'pending_approval',
                    'client_upload', %s, NOW()
                ) RETURNING id
            """, (
                f"Client upload: {file.filename}",
                client_id,
                tenant_id,
            ))
            draft_id = cur.fetchone()["id"]
            conn.commit()
            draft = {"ok": True, "draft_id": draft_id, "status": "pending_approval"}
        except Exception as e:
            conn.rollback()
            draft = {"ok": False, "error": str(e)}
        finally:
            cur.close()
            conn.close()

    return {
        "ok": True,
        "client_id": client_id,
        "tenant_id": tenant_id,
        "filename": file.filename,
        "extracted_fields": fields,
        "draft": draft,
        "message": "დოკუმენტი მიღებულია. ბუღალტერი განიხილავს.",
    }


# ========== Transaction Detail ==========

@router.get("/transactions/{draft_id}")
def client_transaction_detail(draft_id: int, request: Request):
    """
    კლიენტი ხედავს ერთი ტრანზაქციის დეტალებს.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    client_id = request.headers.get("X-Client-ID", "default_client")

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, date, description, amount, status,
                   account_code, confidence, created_at,
                   source_type, debit_account, credit_account
            FROM journal_drafts
            WHERE id = %s AND tenant_id = %s AND partner = %s
        """, (draft_id, tenant_id, client_id))

        row = cur.fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="ტრანზაქცია ვერ მოიძებნა"
            )

        comments = []
        try:
            cur.execute("""
                SELECT author, comment_text, comment_type, created_at
                FROM draft_comments
                WHERE draft_id = %s AND tenant_id = %s
                ORDER BY created_at ASC
            """, (draft_id, tenant_id))
            comments = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

        return {
            "ok": True,
            "transaction": dict(row),
            "comments": comments,
        }
    finally:
        cur.close()
        conn.close()


# ========== Status ==========

@router.get("/status")
def client_portal_status():
    return {
        "ok": True,
        "portal": "active",
        "features": [
            "dashboard — საკუთარი ტრანზაქციების შეჯამება",
            "transactions — ტრანზაქციების სია",
            "upload — დოკუმენტის ატვირთვა",
            "detail — ერთი ტრანზაქციის დეტალი",
        ],
    }