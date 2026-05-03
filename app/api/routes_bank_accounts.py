from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/bank-accounts", tags=["bank-accounts"])

class BankAccountCreate(BaseModel):
    name: str
    bank_name: str
    account_number: str
    currency: Optional[str] = "GEL"
    balance: Optional[float] = 0
    account_type: Optional[str] = "current"
    is_primary: Optional[bool] = False

class BalanceUpdate(BaseModel):
    balance: float
    note: Optional[str] = None

class TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: float
    note: Optional[str] = None

@router.get("/list")
async def list_accounts(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        accounts = [dict(r) for r in await conn.fetch(_q(
            "SELECT * FROM bank_accounts WHERE tenant_id::text = %s ORDER BY is_primary DESC, id"),
            tenant_id)]

    total_gel = sum(float(a["balance"]) for a in accounts if a["currency"] == "GEL")
    return ok_response("Bank accounts", {
        "count": len(accounts),
        "total_gel_balance": round(total_gel, 2),
        "tenant_id": tenant_id,
        "accounts": accounts,
    })

@router.post("/create")
async def create_account(data: BankAccountCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    try:
        async with get_conn() as conn:
            new_id = await conn.fetchval(_q("""
                INSERT INTO bank_accounts (tenant_id, name, bank_name, account_number, currency, balance, account_type, is_primary)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """), tenant_id, data.name, data.bank_name, data.account_number, data.currency,
                data.balance, data.account_type, data.is_primary)
    except Exception as e:
        return error_response("Create failed", "CREATE_ERROR", str(e))
    return ok_response("Account created", {"id": new_id, "tenant_id": tenant_id, **data.dict()})

@router.post("/{account_id}/update-balance")
async def update_balance(account_id: int, data: BalanceUpdate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        acc = await conn.fetchrow(_q(
            "SELECT * FROM bank_accounts WHERE id=%s AND tenant_id::text = %s"),
            account_id, tenant_id)
        if not acc:
            return error_response("Not found", "NOT_FOUND", "")
        old_balance = float(acc["balance"])
        await conn.execute(_q(
            "UPDATE bank_accounts SET balance=%s WHERE id=%s AND tenant_id::text = %s"),
            data.balance, account_id, tenant_id)
    return ok_response("Balance updated", {
        "id": account_id,
        "old_balance": old_balance,
        "new_balance": data.balance,
        "change": round(data.balance - old_balance, 2),
    })

@router.post("/transfer")
async def transfer(req: TransferRequest, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        from_acc = await conn.fetchrow(_q(
            "SELECT * FROM bank_accounts WHERE id=%s AND tenant_id::text = %s"),
            req.from_account_id, tenant_id)
        to_acc = await conn.fetchrow(_q(
            "SELECT * FROM bank_accounts WHERE id=%s AND tenant_id::text = %s"),
            req.to_account_id, tenant_id)

        if not from_acc or not to_acc:
            return error_response("Account not found", "NOT_FOUND", "")
        if float(from_acc["balance"]) < req.amount:
            return error_response("Insufficient balance", "BALANCE_ERROR",
                f"Available: {from_acc['balance']} {from_acc['currency']}")

        async with conn.transaction():
            await conn.execute(_q(
                "UPDATE bank_accounts SET balance=balance-%s WHERE id=%s AND tenant_id::text = %s"),
                req.amount, req.from_account_id, tenant_id)
            await conn.execute(_q(
                "UPDATE bank_accounts SET balance=balance+%s WHERE id=%s AND tenant_id::text = %s"),
                req.amount, req.to_account_id, tenant_id)

    return ok_response("Transfer complete", {
        "from": from_acc["name"],
        "to": to_acc["name"],
        "amount": req.amount,
        "from_new_balance": round(float(from_acc["balance"]) - req.amount, 2),
        "to_new_balance": round(float(to_acc["balance"]) + req.amount, 2),
        "tenant_id": tenant_id,
    })

@router.get("/summary")
async def account_summary(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    async with get_conn() as conn:
        by_currency = [dict(r) for r in await conn.fetch(_q("""
            SELECT currency,
                   COUNT(*) as account_count,
                   COALESCE(SUM(balance),0) as total_balance
            FROM bank_accounts
            WHERE tenant_id::text = %s
            GROUP BY currency ORDER BY total_balance DESC
        """), tenant_id)]
        primary = await conn.fetchrow(_q(
            "SELECT * FROM bank_accounts WHERE is_primary=TRUE AND tenant_id::text = %s LIMIT 1"),
            tenant_id)

    return ok_response("Account summary", {
        "tenant_id": tenant_id,
        "by_currency": [{"currency": r["currency"], "count": r["account_count"],
                         "total": float(r["total_balance"])} for r in by_currency],
        "primary_account": dict(primary) if primary else None,
    })
