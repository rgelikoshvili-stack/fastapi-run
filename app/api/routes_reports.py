from fastapi import APIRouter, Query, Request
from typing import Optional
from app.api.db import get_conn, _q
from app.api.authz import require_permission
from app.api.security import limiter
from app.api.services.ledger_service import (
    get_account_ledger,
    get_trial_balance,
    get_counterparty_ledger,
    get_payroll_ledger,
    get_journal_entries,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/monthly")
async def monthly_report(request: Request):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT DATE_TRUNC('month', created_at) as month,
                   COUNT(*) as total_docs,
                   SUM(CASE WHEN state='APPROVED' THEN 1 ELSE 0 END) as approved,
                   SUM(CASE WHEN state='REJECTED' THEN 1 ELSE 0 END) as rejected
            FROM pipeline_runs
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
            LIMIT 12
        """)
        tx_rows = await conn.fetch(_q("""
            SELECT DATE_TRUNC('month', created_at) as month,
                   SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END) as inflow,
                   SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END) as outflow
            FROM bank_transactions
            WHERE tenant_id = %s
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
            LIMIT 12
        """), tenant_id)

    tx_map = {str(r["month"])[:7]: dict(r) for r in tx_rows}
    result = []
    for r in rows:
        m = str(r["month"])[:7]
        tx = tx_map.get(m, {})
        result.append({
            "month": m,
            "documents": {
                "total": r["total_docs"],
                "approved": r["approved"],
                "rejected": r["rejected"],
            },
            "financials": {
                "inflow": round(float(tx.get("inflow") or 0), 2),
                "outflow": round(float(tx.get("outflow") or 0), 2),
            },
        })
    return {"ok": True, "monthly_reports": result}


@router.get("/annual")
async def annual_report(request: Request):
    require_permission(request, "reports:read")
    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT EXTRACT(YEAR FROM created_at) as year,
                   COUNT(*) as total
            FROM pipeline_runs
            GROUP BY year
            ORDER BY year DESC
        """)
    return {"ok": True, "annual_reports": [dict(r) for r in rows]}


@router.get("/audit-trail")
async def audit_trail(request: Request):
    require_permission(request, "reports:read")
    async with get_conn() as conn:
        rows = await conn.fetch("""
            SELECT run_id, filename, state, created_at
            FROM pipeline_runs
            ORDER BY created_at DESC
            LIMIT 50
        """)
    return {"ok": True, "pipeline_runs": [dict(r) for r in rows]}


@router.get("/pnl")
async def pnl_report(
    request: Request,
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    P&L from journal_drafts using Georgian CoA:
      Revenue (6xxx) = SUM where credit_account LIKE '6%'
      COGS    (5xxx) = SUM where debit_account  LIKE '5%'
      OpEx    (7xxx) = SUM where debit_account  LIKE '7%'
    Only approved / auto_approved / posted drafts are counted.
    """
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conditions = [
        "tenant_id = %s",
        "status IN ('approved','auto_approved','posted')",
        "amount IS NOT NULL",
        "amount > 0",
    ]
    params: list = [tenant_id]

    if date_from:
        conditions.append("date >= %s"); params.append(date_from)
    elif year:
        conditions.append("EXTRACT(YEAR FROM date::date) = %s"); params.append(year)

    if date_to:
        conditions.append("date <= %s"); params.append(date_to)
    elif year and month:
        conditions.append("EXTRACT(MONTH FROM date::date) = %s"); params.append(month)

    where = " AND ".join(conditions)

    async with get_conn() as conn:
        rev_rows = await conn.fetch(_q(f"""
            SELECT
                COALESCE(LEFT(credit_account, 4), 'other') AS acc,
                COALESCE(SUM(amount), 0)                    AS total
            FROM journal_drafts
            WHERE {where}
              AND credit_account ~ '^6'
            GROUP BY 1 ORDER BY total DESC
        """), *params)

        cogs_rows = await conn.fetch(_q(f"""
            SELECT
                COALESCE(LEFT(debit_account, 4), 'other') AS acc,
                COALESCE(SUM(amount), 0)                   AS total
            FROM journal_drafts
            WHERE {where}
              AND debit_account ~ '^5'
            GROUP BY 1 ORDER BY total DESC
        """), *params)

        opex_rows = await conn.fetch(_q(f"""
            SELECT
                COALESCE(LEFT(debit_account, 4), 'other') AS acc,
                COALESCE(SUM(amount), 0)                   AS total
            FROM journal_drafts
            WHERE {where}
              AND debit_account ~ '^7'
            GROUP BY 1 ORDER BY total DESC
        """), *params)

        all_codes = (
            [r["acc"] for r in rev_rows] +
            [r["acc"] for r in cogs_rows] +
            [r["acc"] for r in opex_rows]
        )
        coa_names: dict[str, str] = {}
        if all_codes:
            coa_rows = await conn.fetch("""
                SELECT code, COALESCE(name_en, name_ka, code) AS name
                FROM coa WHERE code = ANY($1)
            """, list(set(all_codes)))
            coa_names = {r["code"]: r["name"] for r in coa_rows}

    def to_lines(rows) -> list[dict]:
        return [
            {
                "account_code": r["acc"],
                "name": coa_names.get(r["acc"], r["acc"]),
                "amount": round(float(r["total"]), 2),
            }
            for r in rows
        ]

    rev_lines  = to_lines(rev_rows)
    cogs_lines = to_lines(cogs_rows)
    opex_lines = to_lines(opex_rows)

    revenue  = round(sum(l["amount"] for l in rev_lines), 2)
    cogs     = round(sum(l["amount"] for l in cogs_lines), 2)
    opex     = round(sum(l["amount"] for l in opex_lines), 2)
    expenses = round(cogs + opex, 2)
    gross    = round(revenue - cogs, 2)
    ebit     = round(gross - opex, 2)
    margin   = round(ebit / revenue * 100, 1) if revenue else 0.0

    breakdown = (
        [{"account_code": l["account_code"], "category": l["name"],
          "amount": l["amount"], "type": "revenue"} for l in rev_lines] +
        [{"account_code": l["account_code"], "category": l["name"],
          "amount": l["amount"], "type": "cogs"} for l in cogs_lines] +
        [{"account_code": l["account_code"], "category": l["name"],
          "amount": l["amount"], "type": "opex"} for l in opex_lines]
    )

    period_from = date_from or (f"{year}-{month:02d}-01" if year and month else (f"{year}-01-01" if year else None))
    period_to   = date_to or None

    return {
        "ok": True,
        "report": "pnl",
        "data": {
            "revenue":          revenue,
            "expenses":         expenses,
            "cogs":             cogs,
            "opex":             opex,
            "gross_profit":     gross,
            "ebit":             ebit,
            "net_profit":       ebit,
            "profit_before_tax": ebit,
            "profit_margin":    margin,
            "breakdown":        breakdown,
            "revenue_detail":   {"total": revenue, "lines": [{"label": l["name"], "account_code": l["account_code"], "amount": l["amount"]} for l in rev_lines]},
            "cogs_detail":      {"total": cogs,    "lines": [{"label": l["name"], "account_code": l["account_code"], "amount": l["amount"]} for l in cogs_lines]},
            "opex_detail":      {"total": opex,    "lines": [{"label": l["name"], "account_code": l["account_code"], "amount": l["amount"]} for l in opex_lines]},
            "period":           {"from": period_from, "to": period_to},
        },
    }


@router.get("/cashflow")
async def cashflow_report(
    request: Request,
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conditions = ["tenant_id = %s", "date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'"]
    params: list = [tenant_id]

    if year:
        conditions.append("EXTRACT(YEAR FROM date::date) = %s")
        params.append(year)
    if month:
        conditions.append("EXTRACT(MONTH FROM date::date) = %s")
        params.append(month)

    where_clause = " AND ".join(conditions)

    async with get_conn() as conn:
        row = await conn.fetchrow(_q(f"""
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) as cash_in,
                COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) as cash_out
            FROM bank_transactions
            WHERE {where_clause}
        """), *params)

    cash_in  = round(float((row or {}).get("cash_in")  or 0), 2)
    cash_out = round(float((row or {}).get("cash_out") or 0), 2)

    return {
        "ok": True,
        "report": "cashflow",
        "data": {
            "cash_in": cash_in,
            "cash_out": cash_out,
            "net_cashflow": round(cash_in - cash_out, 2),
        },
        "note": "ეს არის მარტივი Cash Flow ვერსია bank_transactions-ზე დაყრდნობით.",
    }


@limiter.limit("10/minute")
@router.get("/ledger/{account_code}")
def ledger_report(
    account_code: str,
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")
    data = get_account_ledger(tenant_id, account_code, date_from, date_to)
    return {"ok": True, "report": "ledger", **data}


@limiter.limit("10/minute")
@router.get("/trial-balance")
def trial_balance_report(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")
    data = get_trial_balance(tenant_id, date_from, date_to)
    return {"ok": True, "report": "trial_balance", **data}


@limiter.limit("10/minute")
@router.get("/counterparty/{inn}")
def counterparty_ledger_report(
    inn: str,
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")
    data = get_counterparty_ledger(tenant_id, inn, date_from, date_to)
    return {"ok": True, "report": "counterparty_ledger", **data}


@limiter.limit("10/minute")
@router.get("/payroll")
def payroll_ledger_report(
    request: Request,
    employee_id: Optional[str] = Query(None, description="Employee personal tax number"),
    year: Optional[int] = Query(None),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")
    data = get_payroll_ledger(tenant_id, employee_id, year)
    return {"ok": True, "report": "payroll_ledger", **data}


@limiter.limit("10/minute")
@router.get("/journal")
def journal_report(
    request: Request,
    date: Optional[str] = Query(None, description="YYYY-MM-DD — specific date, or omit for latest"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")
    data = get_journal_entries(tenant_id, date, limit, offset)
    return {"ok": True, "report": "journal", **data}


@router.get("/pnl/detail")
async def pnl_detail(
    request: Request,
    account_code: Optional[str] = Query(None, description="e.g. 7100"),
    debit_account: Optional[str] = Query(None),
    credit_account: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Drill-down: click a P&L row → see individual journal drafts behind the number."""
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conditions = ["tenant_id = %s", "status IN ('approved','auto_approved','posted')"]
    params: list = [tenant_id]
    if account_code:
        conditions.append("account_code = %s"); params.append(account_code)
    if debit_account:
        conditions.append("debit_account = %s"); params.append(debit_account)
    if credit_account:
        conditions.append("credit_account = %s"); params.append(credit_account)
    if date_from:
        conditions.append("date >= %s"); params.append(date_from)
    if date_to:
        conditions.append("date <= %s"); params.append(date_to)
    where = " AND ".join(conditions)

    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, date, description, partner, amount,
                   account_code, debit_account, credit_account, status, source_type, created_at
            FROM journal_drafts
            WHERE {where}
            ORDER BY date DESC, id DESC
            LIMIT %s OFFSET %s
        """), *params, limit, offset)]
        agg = dict(await conn.fetchrow(_q(f"""
            SELECT COUNT(*) AS total, COALESCE(SUM(amount), 0) AS total_amount
            FROM journal_drafts WHERE {where}
        """), *params))

    return {
        "ok": True,
        "filters": {"account_code": account_code, "debit_account": debit_account,
                    "credit_account": credit_account, "date_from": date_from, "date_to": date_to},
        "summary": {"count": int(agg["total"]), "total_amount": round(float(agg["total_amount"]), 2)},
        "transactions": rows,
    }


@router.get("/balance-sheet")
@limiter.limit("30/minute")
async def balance_sheet(
    request: Request,
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD, default today"),
):
    """
    Balance Sheet as of a given date using Georgian CoA:
      Assets      (1xxx) = net debit balances
      Liabilities (3xxx) = net credit balances
      Equity      (5xxx) = net credit balances
    """
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    date_filter = f"AND date::date <= '{as_of}'" if as_of else ""

    async with get_conn() as conn:
        async def fetch_group(pattern: str, side: str) -> list:
            col = "debit_account" if side == "debit" else "credit_account"
            return await conn.fetch(_q(f"""
                SELECT
                    LEFT({col}, 4)                              AS acc,
                    COALESCE(SUM(amount), 0)                    AS total
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND status IN ('approved','auto_approved','posted')
                  AND amount IS NOT NULL AND amount > 0
                  AND {col} ~ %s
                  {date_filter}
                GROUP BY 1 ORDER BY total DESC
            """), tenant_id, pattern)

        asset_rows  = await fetch_group(r'^1', 'debit')
        liab_rows   = await fetch_group(r'^3', 'credit')
        equity_rows = await fetch_group(r'^5', 'credit')

        all_codes = [r["acc"] for r in list(asset_rows) + list(liab_rows) + list(equity_rows)]
        coa_names: dict = {}
        if all_codes:
            coa_rows = await conn.fetch(
                "SELECT code, COALESCE(name_en, name_ka, code) AS name FROM coa WHERE code = ANY($1)",
                list(set(all_codes))
            )
            coa_names = {r["code"]: r["name"] for r in coa_rows}

    def to_lines(rows) -> list:
        return [{"account_code": r["acc"], "name": coa_names.get(r["acc"], r["acc"]),
                 "amount": round(float(r["total"]), 2)} for r in rows]

    asset_lines  = to_lines(asset_rows)
    liab_lines   = to_lines(liab_rows)
    equity_lines = to_lines(equity_rows)

    total_assets      = round(sum(l["amount"] for l in asset_lines), 2)
    total_liabilities = round(sum(l["amount"] for l in liab_lines), 2)
    total_equity      = round(sum(l["amount"] for l in equity_lines), 2)
    balanced          = abs(total_assets - total_liabilities - total_equity) < 0.02

    import logging as _log
    if not balanced:
        _log.getLogger(__name__).warning(
            "balance_sheet_unbalanced tenant=%s assets=%.2f liab=%.2f eq=%.2f diff=%.2f",
            tenant_id, total_assets, total_liabilities, total_equity,
            total_assets - total_liabilities - total_equity,
        )

    return {
        "ok": True,
        "report": "balance_sheet",
        "data": {
            "as_of": as_of or "today",
            "assets":      {"total": total_assets,      "lines": asset_lines},
            "liabilities": {"total": total_liabilities, "lines": liab_lines},
            "equity":      {"total": total_equity,      "lines": equity_lines},
            "balanced":    balanced,
            "check":       round(total_assets - total_liabilities - total_equity, 2),
        },
    }


@router.get("/bs/detail")
async def bs_detail(
    request: Request,
    account_code: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Drill-down: Balance Sheet account → individual transactions."""
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conditions = ["tenant_id = %s"]
    params: list = [tenant_id]
    if account_code:
        conditions.append("(debit_account = %s OR credit_account = %s OR account_code = %s)")
        params += [account_code, account_code, account_code]
    if date_from:
        conditions.append("date >= %s"); params.append(date_from)
    if date_to:
        conditions.append("date <= %s"); params.append(date_to)
    where = " AND ".join(conditions)

    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, date, description, partner, amount,
                   account_code, debit_account, credit_account, status, created_at
            FROM journal_drafts
            WHERE {where}
            ORDER BY date DESC, id DESC
            LIMIT %s OFFSET %s
        """), *params, limit, offset)]
        agg = dict(await conn.fetchrow(_q(f"""
            SELECT COUNT(*) AS total, COALESCE(SUM(amount), 0) AS total_amount
            FROM journal_drafts WHERE {where}
        """), *params))

    return {
        "ok": True,
        "account_code": account_code,
        "summary": {"count": int(agg["total"]), "total_amount": round(float(agg["total_amount"]), 2)},
        "transactions": rows,
    }


@router.get("/cashflow/detail")
async def cashflow_detail(
    request: Request,
    direction: Optional[str] = Query(None, description="in | out"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Drill-down: Cash Flow in/out → individual bank transactions."""
    require_permission(request, "reports:read")
    tenant_id = getattr(request.state, "tenant_id", "default")

    conditions = ["tenant_id = %s", "date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'"]
    params: list = [tenant_id]
    if direction == "in":
        conditions.append("amount > 0")
    elif direction == "out":
        conditions.append("amount < 0")
    if date_from:
        conditions.append("date::date >= %s"); params.append(date_from)
    if date_to:
        conditions.append("date::date <= %s"); params.append(date_to)
    where = " AND ".join(conditions)

    async with get_conn() as conn:
        rows = [dict(r) for r in await conn.fetch(_q(f"""
            SELECT id, date, description, amount, currency, created_at
            FROM bank_transactions
            WHERE {where}
            ORDER BY date DESC, id DESC
            LIMIT %s OFFSET %s
        """), *params, limit, offset)]
        agg = dict(await conn.fetchrow(_q(f"""
            SELECT COUNT(*) AS total, COALESCE(SUM(ABS(amount)), 0) AS total_amount
            FROM bank_transactions WHERE {where}
        """), *params))

    return {
        "ok": True,
        "direction": direction,
        "summary": {"count": int(agg["total"]), "total_amount": round(float(agg["total_amount"]), 2)},
        "transactions": rows,
    }
