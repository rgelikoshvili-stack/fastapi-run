from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
import psycopg2.extras
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/statements", tags=["statements"])

class StatementRequest(BaseModel):
    year: int
    month: Optional[int] = None

@router.post("/pnl")
def profit_and_loss(req: StatementRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        period = f"{req.year}-{str(req.month).zfill(2)}%" if req.month else f"{req.year}%"

        # შემოსავალი
        cur.execute("""
            SELECT COALESCE(reason,'other') as category, account_code,
                   COALESCE(SUM(amount),0) as total
            FROM journal_drafts
            WHERE account_code LIKE '6%%' AND date LIKE %s
            GROUP BY reason, account_code ORDER BY total DESC
        """, (period,))
        income_rows = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT COALESCE(reason,'other') as category, account_code,
                   COALESCE(SUM(amount),0) as total
            FROM journal_drafts
            WHERE account_code LIKE '7%%' AND date LIKE %s
            GROUP BY reason, account_code ORDER BY total DESC
        """, (period,))
        expense_rows = [dict(r) for r in cur.fetchall()]

        cur.execute("""
            SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts
            WHERE account_code='3100' AND date LIKE %s
        """, (period,))
        row = cur.fetchone()
        tax = float(row["total"]) if row else 0.0

    finally:
        cur.close(); conn.close()

    total_income = sum(float(r["total"]) for r in income_rows)
    total_expense = sum(float(r["total"]) for r in expense_rows)
    gross_profit = round(total_income - total_expense, 2)
    net_profit = round(gross_profit - tax, 2)
    margin = round(net_profit / total_income * 100, 1) if total_income else 0

    return ok_response("Profit & Loss Statement", {
        "period": f"{req.year}" + (f"-{str(req.month).zfill(2)}" if req.month else ""),
        "income": {
            "items": [{"category": r["category"], "account": r["account_code"],
                       "amount": float(r["total"])} for r in income_rows],
            "total": round(total_income, 2)
        },
        "expenses": {
            "items": [{"category": r["category"], "account": r["account_code"],
                       "amount": float(r["total"])} for r in expense_rows],
            "total": round(total_expense, 2)
        },
        "gross_profit": gross_profit,
        "tax": round(tax, 2),
        "net_profit": net_profit,
        "profit_margin_pct": margin,
        "status": "profit" if net_profit > 0 else "loss"
    })

@router.post("/balance-sheet")
def balance_sheet(req: StatementRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # აქტივები — საბანკო ანგარიშები
        cur.execute("SELECT name, currency, balance FROM bank_accounts ORDER BY is_primary DESC")
        bank_accounts = [dict(r) for r in cur.fetchall()]

        # დებიტორული — გადაუხდელი ინვოისები
        cur.execute("SELECT COALESCE(SUM(total),0) as total, COUNT(*) as cnt FROM invoices WHERE status='sent'")
        receivables = dict(cur.fetchone())

        # გადასახდელი — pending expenses
        cur.execute("SELECT COALESCE(SUM(amount),0) as total, COUNT(*) as cnt FROM expenses WHERE status='pending'")
        payables = dict(cur.fetchone())

        # შემოსავალი/ხარჯი journal-იდან
        cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '6%'")
        retained = float(cur.fetchone()["total"])
        cur.execute("SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '7%'")
        expenses_total = float(cur.fetchone()["total"])

    finally:
        cur.close(); conn.close()

    total_cash = sum(float(a["balance"]) for a in bank_accounts if a["currency"] == "GEL")
    total_receivables = float(receivables["total"])
    total_assets = round(total_cash + total_receivables, 2)
    total_payables = float(payables["total"])
    equity = round(retained - expenses_total, 2)
    total_liabilities_equity = round(total_payables + equity, 2)

    return ok_response("Balance Sheet", {
        "period": f"{req.year}" + (f"-{str(req.month).zfill(2)}" if req.month else ""),
        "assets": {
            "cash_and_bank": [{"name": a["name"], "currency": a["currency"],
                               "balance": float(a["balance"])} for a in bank_accounts],
            "total_cash_gel": round(total_cash, 2),
            "accounts_receivable": round(total_receivables, 2),
            "total_assets": total_assets,
        },
        "liabilities": {
            "accounts_payable": round(total_payables, 2),
            "total_liabilities": round(total_payables, 2),
        },
        "equity": {
            "retained_earnings": round(retained, 2),
            "total_expenses": round(expenses_total, 2),
            "net_equity": equity,
        },
        "total_liabilities_and_equity": total_liabilities_equity,
        "balanced": abs(total_assets - total_liabilities_equity) < 1
    })

@router.post("/cashflow")
def cash_flow(req: StatementRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        period = f"{req.year}-{str(req.month).zfill(2)}%" if req.month else f"{req.year}%"
        cur.execute("""
            SELECT reason, account_code,
                   COALESCE(SUM(amount),0) as total
            FROM journal_drafts WHERE date LIKE %s
            GROUP BY reason, account_code ORDER BY account_code
        """, (period,))
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        cur.close(); conn.close()

    operating_in = sum(float(r["total"]) for r in rows if r["account_code"].startswith("6"))
    operating_out = sum(float(r["total"]) for r in rows if r["account_code"].startswith("7"))
    tax_out = sum(float(r["total"]) for r in rows if r["account_code"] == "3100")
    transfers = sum(float(r["total"]) for r in rows if r["account_code"] == "1210")
    net_operating = round(operating_in - operating_out - tax_out, 2)

    return ok_response("Cash Flow Statement", {
        "period": f"{req.year}" + (f"-{str(req.month).zfill(2)}" if req.month else ""),
        "operating": {
            "cash_inflows": round(operating_in, 2),
            "cash_outflows": round(operating_out, 2),
            "tax_payments": round(tax_out, 2),
            "net_operating_cashflow": net_operating,
        },
        "financing": {
            "transfers": round(transfers, 2),
        },
        "net_cashflow": round(net_operating, 2),
        "status": "positive" if net_operating > 0 else "negative"
    })
