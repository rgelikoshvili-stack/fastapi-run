from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/reconcile", tags=["reconcile"])

class ReconcileRequest(BaseModel):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    tenant_code: Optional[str] = None

@router.post("/run")
def run_reconciliation(req: ReconcileRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM journal_drafts WHERE 1=1"
        params = []
        if req.date_from:
            query += " AND date >= %s"; params.append(req.date_from)
        if req.date_to:
            query += " AND date <= %s"; params.append(req.date_to)
        cur.execute(query, params)
        drafts = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    total_debit = sum(d["amount"] or 0 for d in drafts if d.get("debit_account","").startswith("7") or d.get("debit_account","").startswith("3"))
    total_credit = sum(d["amount"] or 0 for d in drafts if d.get("credit_account","") == "6100")
    balance = total_credit - total_debit
    unmatched = [d for d in drafts if d.get("status") == "pending_approval"]
    duplicates = []
    seen = {}
    for d in drafts:
        key = f"{d.get('date')}_{d.get('description')}_{d.get('amount')}"
        if key in seen:
            duplicates.append({"id": d["id"], "duplicate_of": seen[key]})
        else:
            seen[key] = d["id"]

    status = "balanced" if abs(balance) < 0.01 else "unbalanced"

    return ok_response("Reconciliation complete", {
        "period": {"from": req.date_from, "to": req.date_to},
        "total_transactions": len(drafts),
        "total_income": round(total_credit, 2),
        "total_expense": round(total_debit, 2),
        "balance": round(balance, 2),
        "status": status,
        "unmatched_count": len(unmatched),
        "duplicate_count": len(duplicates),
        "duplicates": duplicates[:10],
    })

@router.get("/summary")
def reconciliation_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT 
                account_code,
                reason,
                COUNT(*) as tx_count,
                SUM(amount) as total_amount,
                AVG(confidence) as avg_confidence
            FROM journal_drafts
            GROUP BY account_code, reason
            ORDER BY total_amount DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
    except Exception as e:
        return error_response("DB error", "DB_ERROR", str(e))
    finally:
        cur.close(); conn.close()

    return ok_response("Reconciliation summary", {
        "by_account": rows,
        "total_accounts": len(rows)
    })
