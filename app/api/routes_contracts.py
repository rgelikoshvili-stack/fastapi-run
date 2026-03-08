from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit import log_event
from datetime import date, datetime

router = APIRouter(prefix="/contracts", tags=["contracts"])

class ContractCreate(BaseModel):
    title: str
    party_name: str
    party_tax_id: Optional[str] = None
    contract_type: Optional[str] = "service"
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    value: Optional[float] = 0
    currency: Optional[str] = "GEL"
    payment_terms: Optional[str] = None
    auto_renew: Optional[bool] = False
    notes: Optional[str] = None

class ContractStatusUpdate(BaseModel):
    status: str

class MilestoneCreate(BaseModel):
    title: str
    due_date: str
    amount: Optional[float] = 0
    notes: Optional[str] = None

@router.get("/list")
def list_contracts(status: Optional[str] = None, contract_type: Optional[str] = None):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM contracts WHERE 1=1"
        params = []
        if status:
            query += " AND status=%s"; params.append(status)
        if contract_type:
            query += " AND contract_type=%s"; params.append(contract_type)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        contracts = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Contracts", {"count": len(contracts), "contracts": contracts})

@router.post("/create")
def create_contract(data: ContractCreate):
    conn = get_db()
    cur = conn.cursor()
    try:
        from datetime import datetime
        num = f"CNT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        cur.execute("""
            INSERT INTO contracts (contract_number, title, party_name, party_tax_id,
                contract_type, start_date, end_date, value, currency,
                payment_terms, auto_renew, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (num, data.title, data.party_name, data.party_tax_id,
              data.contract_type, data.start_date, data.end_date,
              data.value, data.currency, data.payment_terms,
              data.auto_renew, data.notes))
        new_id = cur.fetchone()[0]
        conn.commit()
        log_event("contract.create", "contracts", str(new_id),
                  new_value={"number": num, "party": data.party_name, "value": data.value})
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Contract created", {"id": new_id, "contract_number": num, **data.dict()})

@router.get("/{contract_id}")
def get_contract(contract_id: int):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM contracts WHERE id=%s", (contract_id,))
        contract = cur.fetchone()
        if not contract:
            return error_response("Not found", "NOT_FOUND", "")
        cur.execute("SELECT * FROM contract_milestones WHERE contract_id=%s ORDER BY due_date", (contract_id,))
        milestones = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Contract", {**dict(contract), "milestones": milestones})

@router.post("/{contract_id}/status")
def update_status(contract_id: int, data: ContractStatusUpdate):
    valid = ["draft", "active", "expired", "terminated", "renewed"]
    if data.status not in valid:
        return error_response("Invalid status", "VALIDATION_ERROR", f"Use: {valid}")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE contracts SET status=%s WHERE id=%s", (data.status, contract_id))
        conn.commit()
        log_event("contract.status_change", "contracts", str(contract_id),
                  new_value={"status": data.status})
    except Exception as e:
        conn.rollback()
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Status updated", {"id": contract_id, "status": data.status})

@router.post("/{contract_id}/milestones")
def add_milestone(contract_id: int, data: MilestoneCreate):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO contract_milestones (contract_id, title, due_date, amount, notes)
            VALUES (%s,%s,%s,%s,%s) RETURNING id
        """, (contract_id, data.title, data.due_date, data.amount, data.notes))
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Milestone added", {"id": new_id, "contract_id": contract_id, "title": data.title})

@router.get("/summary/stats")
def contract_summary():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT status, COUNT(*) as cnt, COALESCE(SUM(value),0) as total FROM contracts GROUP BY status")
        by_status = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT contract_type, COUNT(*) as cnt FROM contracts GROUP BY contract_type")
        by_type = {r["contract_type"]: r["cnt"] for r in cur.fetchall()}
        cur.execute("SELECT COUNT(*) as cnt FROM contracts WHERE end_date <= CURRENT_DATE + INTERVAL '30 days' AND status='active'")
        expiring_soon = cur.fetchone()["cnt"]
        cur.execute("SELECT COALESCE(SUM(value),0) as total FROM contracts WHERE status='active'")
        active_value = float(cur.fetchone()["total"])
    finally:
        cur.close(); conn.close()
    return ok_response("Contract summary", {
        "active_value": active_value,
        "expiring_soon_30d": expiring_soon,
        "by_status": by_status,
        "by_type": by_type
    })
