from fastapi import APIRouter, Request
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
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
def list_accounts(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM bank_accounts WHERE tenant_id=%s ORDER BY is_primary DESC, id",
            (tenant_id,),
        )
        accounts = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    total_gel = sum(float(a["balance"]) for a in accounts if a["currency"] == "GEL")
    return ok_response("Bank accounts", {
        "count": len(accounts),
        "total_gel_balance": round(total_gel, 2),
        "tenant_id": tenant_id,
        "accounts": accounts,
    })

@router.post("/create")
def create_account(data: BankAccountCreate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO bank_accounts (tenant_id, name, bank_name, account_number, currency, balance, account_type, is_primary)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (tenant_id, data.name, data.bank_name, data.account_number, data.currency,
              data.balance, data.account_type, data.is_primary))
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        return error_response("Create failed", "CREATE_ERROR", str(e))
    finally:
        cur.close(); conn.close()
    return ok_response("Account created", {"id": new_id, "tenant_id": tenant_id, **data.dict()})

@router.post("/{account_id}/update-balance")
def update_balance(account_id: int, data: BalanceUpdate, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM bank_accounts WHERE id=%s AND tenant_id=%s",
            (account_id, tenant_id),
        )
        acc = cur.fetchone()
        if not acc:
            return error_response("Not found", "NOT_FOUND", "")
        old_balance = float(acc["balance"])
        cur2 = conn.cursor()
        cur2.execute(
            "UPDATE bank_accounts SET balance=%s WHERE id=%s AND tenant_id=%s",
            (data.balance, account_id, tenant_id),
        )
        conn.commit()
    finally:
        cur.close(); conn.close()
    return ok_response("Balance updated", {
        "id": account_id,
        "old_balance": old_balance,
        "new_balance": data.balance,
        "change": round(data.balance - old_balance, 2),
    })

@router.post("/transfer")
def transfer(req: TransferRequest, request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM bank_accounts WHERE id=%s AND tenant_id=%s",
            (req.from_account_id, tenant_id),
        )
        from_acc = cur.fetchone()
        cur.execute(
            "SELECT * FROM bank_accounts WHERE id=%s AND tenant_id=%s",
            (req.to_account_id, tenant_id),
        )
        to_acc = cur.fetchone()

        if not from_acc or not to_acc:
            return error_response("Account not found", "NOT_FOUND", "")
        if float(from_acc["balance"]) < req.amount:
            return error_response("Insufficient balance", "BALANCE_ERROR",
                f"Available: {from_acc['balance']} {from_acc['currency']}")

        cur2 = conn.cursor()
        cur2.execute(
            "UPDATE bank_accounts SET balance=balance-%s WHERE id=%s AND tenant_id=%s",
            (req.amount, req.from_account_id, tenant_id),
        )
        cur2.execute(
            "UPDATE bank_accounts SET balance=balance+%s WHERE id=%s AND tenant_id=%s",
            (req.amount, req.to_account_id, tenant_id),
        )
        conn.commit()
    finally:
        cur.close(); conn.close()

    return ok_response("Transfer complete", {
        "from": from_acc["name"],
        "to": to_acc["name"],
        "amount": req.amount,
        "from_new_balance": round(float(from_acc["balance"]) - req.amount, 2),
        "to_new_balance": round(float(to_acc["balance"]) + req.amount, 2),
        "tenant_id": tenant_id,
    })

@router.get("/summary")
def account_summary(request: Request):
    tenant_id = getattr(request.state, "tenant_id", "default")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT currency,
                   COUNT(*) as account_count,
                   COALESCE(SUM(balance),0) as total_balance
            FROM bank_accounts
            WHERE tenant_id=%s
            GROUP BY currency ORDER BY total_balance DESC
        """, (tenant_id,))
        by_currency = [dict(r) for r in cur.fetchall()]
        cur.execute(
            "SELECT * FROM bank_accounts WHERE is_primary=TRUE AND tenant_id=%s LIMIT 1",
            (tenant_id,),
        )
        primary = cur.fetchone()
    finally:
        cur.close(); conn.close()

    return ok_response("Account summary", {
        "tenant_id": tenant_id,
        "by_currency": [{"currency": r["currency"], "count": r["account_count"],
                         "total": float(r["total_balance"])} for r in by_currency],
        "primary_account": dict(primary) if primary else None,
    })
