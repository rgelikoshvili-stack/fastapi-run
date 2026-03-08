from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
import httpx
from app.api.response_utils import ok_response, error_response
from app.api.db import get_db
import psycopg2.extras

router = APIRouter(prefix="/balance-ge", tags=["balance-ge"])

BALANCE_GE_URL = "https://api.balance.ge/v1"

class BalanceGeConfig(BaseModel):
    api_key: str
    company_id: Optional[str] = "default"

class JournalPostRequest(BaseModel):
    draft_ids: List[int]
    api_key: str
    company_id: Optional[str] = "default"

@router.post("/test-connection")
async def test_connection(config: BalanceGeConfig):
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{BALANCE_GE_URL}/company/{config.company_id}",
                headers={"Authorization": f"Bearer {config.api_key}"}
            )
            if r.status_code == 200:
                return ok_response("Balance.ge connected", r.json())
            else:
                return error_response(
                    "Connection failed",
                    "AUTH_ERROR",
                    f"Status: {r.status_code}"
                )
    except Exception as e:
        return error_response("Connection error", "CONNECT_ERROR", str(e))

@router.post("/post-journals")
async def post_journals(req: JournalPostRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM journal_drafts WHERE id = ANY(%s) AND status='approved'",
            (req.draft_ids,)
        )
        drafts = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    if not drafts:
        return error_response("No approved drafts found", "NOT_FOUND", "")

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
                        "Authorization": f"Bearer {req.api_key}",
                        "X-Company-ID": req.company_id
                    }
                )
                if r.status_code in (200, 201):
                    posted.append({"id": d["id"], "status": "posted"})
                else:
                    failed.append({"id": d["id"], "error": r.text[:200]})
            except Exception as e:
                failed.append({"id": d["id"], "error": str(e)})

    return ok_response("Balance.ge posting complete", {
        "posted_count": len(posted),
        "failed_count": len(failed),
        "posted": posted,
        "failed": failed,
    })

@router.get("/export-format/{draft_id}")
async def export_format(draft_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM journal_drafts WHERE id=%s", (draft_id,))
        d = cur.fetchone()
    finally:
        cur.close(); conn.close()

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
    }
    return ok_response("Balance.ge format", balance_ge_format)
