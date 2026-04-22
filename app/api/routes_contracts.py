from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response
from app.api.audit import log_event
from datetime import datetime

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
def list_contracts(request: Request, status: Optional[str] = None, contract_type: Optional[str] = None):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        query = "SELECT * FROM contracts WHERE tenant_id = %s"
        params = [tenant_id]
        if status:
            query += " AND status=%s"; params.append(status)
        if contract_type:
            query += " AND contract_type=%s"; params.append(contract_type)
        query += " ORDER BY created_at DESC"
        cur.execute(query, params)
        contracts = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Contracts", {"count": len(contracts), "tenant_id": tenant_id, "contracts": contracts})

@router.post("/create")
def create_contract(data: ContractCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor()
    try:
        num = f"CNT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        cur.execute("""
            INSERT INTO contracts (tenant_id, contract_number, title, party_name, party_tax_id,
                contract_type, start_date, end_date, value, currency,
                payment_terms, auto_renew, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (tenant_id, num, data.title, data.party_name, data.party_tax_id,
              data.contract_type, data.start_date, data.end_date,
              data.value, data.currency, data.payment_terms,
              data.auto_renew, data.notes))
        new_id = cur.fetchone()[0]
        conn.commit()
        log_event("contract.create", "contracts", str(new_id), tenant_id=tenant_id,
                  new_value={"number": num, "party": data.party_name, "value": data.value})
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Contract created", {"id": new_id, "contract_number": num, "tenant_id": tenant_id, **data.dict()})

@router.get("/summary/stats")
def contract_summary(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT status, COUNT(*) as cnt, COALESCE(SUM(value),0) as total FROM contracts WHERE tenant_id=%s GROUP BY status",
            (tenant_id,),
        )
        by_status = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT contract_type, COUNT(*) as cnt FROM contracts WHERE tenant_id=%s GROUP BY contract_type",
            (tenant_id,),
        )
        by_type = {r["contract_type"]: r["cnt"] for r in cur.fetchall()}
        cur.execute(
            "SELECT COUNT(*) as cnt FROM contracts WHERE end_date <= CURRENT_DATE + INTERVAL '30 days' AND status='active' AND tenant_id=%s",
            (tenant_id,),
        )
        expiring_soon = cur.fetchone()["cnt"]
        cur.execute(
            "SELECT COALESCE(SUM(value),0) as total FROM contracts WHERE status='active' AND tenant_id=%s",
            (tenant_id,),
        )
        active_value = float(cur.fetchone()["total"])
    finally:
        cur.close(); conn.close()
    return ok_response("Contract summary", {
        "tenant_id": tenant_id,
        "active_value": active_value,
        "expiring_soon_30d": expiring_soon,
        "by_status": by_status,
        "by_type": by_type,
        "total": sum(s["cnt"] for s in by_status),
        "active": next((s["cnt"] for s in by_status if s["status"] == "active"), 0),
        "draft": next((s["cnt"] for s in by_status if s["status"] == "draft"), 0),
        "expired": next((s["cnt"] for s in by_status if s["status"] == "expired"), 0),
    })

@router.get("/{contract_id}")
def get_contract(contract_id: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM contracts WHERE id=%s AND tenant_id=%s", (contract_id, tenant_id))
        contract = cur.fetchone()
        if not contract:
            return error_response("Not found", "NOT_FOUND", "")
        cur.execute(
            "SELECT * FROM contract_milestones WHERE contract_id=%s AND tenant_id=%s ORDER BY due_date",
            (contract_id, tenant_id),
        )
        milestones = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()
    return ok_response("Contract", {**dict(contract), "milestones": milestones})

@router.post("/{contract_id}/status")
def update_status(contract_id: int, data: ContractStatusUpdate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    valid = ["draft", "active", "expired", "terminated", "renewed"]
    if data.status not in valid:
        return error_response("Invalid status", "VALIDATION_ERROR", f"Use: {valid}")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE contracts SET status=%s WHERE id=%s AND tenant_id=%s",
            (data.status, contract_id, tenant_id),
        )
        if cur.rowcount == 0:
            return error_response("Not found", "NOT_FOUND", "")
        conn.commit()
        log_event("contract.status_change", "contracts", str(contract_id), tenant_id=tenant_id,
                  new_value={"status": data.status})
    except Exception as e:
        conn.rollback()
        return error_response("Update failed", "UPDATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Status updated", {"id": contract_id, "status": data.status})

@router.post("/{contract_id}/milestones")
def add_milestone(contract_id: int, data: MilestoneCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM contracts WHERE id=%s AND tenant_id=%s", (contract_id, tenant_id))
        if not cur.fetchone():
            return error_response("Not found", "NOT_FOUND", "Contract not found for this tenant")
        cur.execute("""
            INSERT INTO contract_milestones (tenant_id, contract_id, title, due_date, amount, notes)
            VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
        """, (tenant_id, contract_id, data.title, data.due_date, data.amount, data.notes))
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Milestone added", {"id": new_id, "contract_id": contract_id, "title": data.title})
