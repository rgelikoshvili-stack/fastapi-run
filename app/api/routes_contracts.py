from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.api.db import get_conn, _q
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
async def list_contracts(request: Request, status: Optional[str] = None, contract_type: Optional[str] = None):
    tenant_id = getattr(request.state, "tenant_id", "default")
    sql = "SELECT * FROM contracts WHERE tenant_id = $1"
    params: list = [tenant_id]
    if status:
        params.append(status); sql += f" AND status=${len(params)}"
    if contract_type:
        params.append(contract_type); sql += f" AND contract_type=${len(params)}"
    sql += " ORDER BY created_at DESC"
    async with get_conn() as conn:
        contracts = [dict(r) for r in await conn.fetch(sql, *params)]
    return ok_response("Contracts", {"count": len(contracts), "tenant_id": tenant_id, "contracts": contracts})

@router.post("/create")
async def create_contract(data: ContractCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    num = f"CNT-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    async with get_conn() as conn:
        try:
            new_id = await conn.fetchval(_q("""
                INSERT INTO contracts (tenant_id, contract_number, title, party_name, party_tax_id,
                    contract_type, start_date, end_date, value, currency, payment_terms, auto_renew, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """), tenant_id, num, data.title, data.party_name, data.party_tax_id,
                data.contract_type, data.start_date, data.end_date, data.value,
                data.currency, data.payment_terms, data.auto_renew, data.notes)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Contract created", {"id": new_id, "contract_number": num, "tenant_id": tenant_id})

@router.get("/{contract_id}")
async def get_contract(contract_id: int, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT * FROM contracts WHERE id=%s AND tenant_id=%s"), contract_id, tenant_id)
        if not row:
            return error_response("Not found", "NOT_FOUND", "")
        milestones = [dict(r) for r in await conn.fetch(_q(
            "SELECT * FROM contract_milestones WHERE contract_id=%s AND tenant_id=%s ORDER BY due_date"), contract_id, tenant_id)]
    return ok_response("Contract", {**dict(row), "milestones": milestones})

@router.post("/{contract_id}/status")
async def update_status(contract_id: int, data: ContractStatusUpdate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        try:
            st = await conn.execute(_q("UPDATE contracts SET status=%s WHERE id=%s AND tenant_id=%s"),
                                    data.status, contract_id, tenant_id)
            if int(st.split()[-1]) == 0:
                return error_response("Not found", "NOT_FOUND", "")
        except Exception as e:
            return error_response("Update failed", "UPDATE_ERROR", str(e))
    return ok_response("Status updated", {"id": contract_id, "status": data.status})

@router.post("/{contract_id}/milestones")
async def add_milestone(contract_id: int, data: MilestoneCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        owner = await conn.fetchrow(_q("SELECT id FROM contracts WHERE id=%s AND tenant_id=%s"), contract_id, tenant_id)
        if not owner:
            return error_response("Contract not found", "NOT_FOUND", "")
        try:
            new_id = await conn.fetchval(_q("""
                INSERT INTO contract_milestones (tenant_id, contract_id, title, due_date, amount, notes)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
            """), tenant_id, contract_id, data.title, data.due_date, data.amount, data.notes)
        except Exception as e:
            return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Milestone added", {"id": new_id, "contract_id": contract_id})

@router.get("/stats/summary")
async def contract_stats(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        total = await conn.fetchval(_q("SELECT COUNT(*) FROM contracts WHERE tenant_id=%s"), tenant_id) or 0
        total_value = await conn.fetchval(_q("SELECT COALESCE(SUM(value),0) FROM contracts WHERE tenant_id=%s"), tenant_id) or 0
        by_status = {r["status"]: r["cnt"] for r in await conn.fetch(_q(
            "SELECT status, COUNT(*) as cnt FROM contracts WHERE tenant_id=%s GROUP BY status"), tenant_id)}
    return ok_response("Contract stats", {"total": total, "total_value": float(total_value), "by_status": by_status})
