from fastapi import APIRouter, Query, Request
import logging
from typing import Optional
from app.api.db import get_conn, _q
from app.api.authz import require_permission
from app.api.security import limiter
from app.api.response_utils import ok_response, error_response, http_error
from app.api.tenant_context import resolve_tenant_id
from app.api.services.ledger_service import (
    get_account_ledger,
    get_trial_balance,
    get_counterparty_ledger,
    get_payroll_ledger,
    get_journal_entries,
)
from app.api.services.payroll_service import normalize_payroll_report_filters
from app.api.observability import structured_log

router = APIRouter(prefix="/reports", tags=["reports"])
log = logging.getLogger(__name__)


@router.get("/monthly")
async def monthly_report(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    async with get_conn() as conn:
        rows = await conn.fetch(_q("""
            SELECT DATE_TRUNC('month', created_at) as month,
                   COUNT(*) as total_docs,
                   SUM(CASE WHEN state='APPROVED' THEN 1 ELSE 0 END) as approved,
                   SUM(CASE WHEN state='REJECTED' THEN 1 ELSE 0 END) as rejected
            FROM pipeline_runs
            WHERE tenant_id = %s
            GROUP BY DATE_TRUNC('month', created_at)
            ORDER BY month DESC
            LIMIT 12
        """), tenant_id)
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
    return ok_response("Monthly reports", {"monthly_reports": result})


@limiter.limit("10/minute")
@router.get("/annual")
async def annual_report(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        rows = await conn.fetch(_q("""
            SELECT EXTRACT(YEAR FROM created_at) as year,
                   COUNT(*) as total
            FROM pipeline_runs
            WHERE tenant_id = %s
            GROUP BY year
            ORDER BY year DESC
        """), tenant_id)
    return ok_response("Annual reports", {"annual_reports": [dict(r) for r in rows]})


@limiter.limit("10/minute")
@router.get("/audit-trail")
async def audit_trail(request: Request):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        rows = await conn.fetch(_q("""
            SELECT run_id, filename, state, created_at
            FROM pipeline_runs
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 50
        """), tenant_id)
    return ok_response("Audit trail", {"pipeline_runs": [dict(r) for r in rows]})



@router.get("/cashflow")
async def cashflow_report(
    request: Request,
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

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

    return ok_response("Cashflow report", {
        "report": "cashflow",
        "data": {
            "cash_in": cash_in,
            "cash_out": cash_out,
            "net_cashflow": round(cash_in - cash_out, 2),
        },
        "note": "ეს არის მარტივი Cash Flow ვერსია bank_transactions-ზე დაყრდნობით.",
    })


@limiter.limit("10/minute")
@router.get("/ledger/{account_code}")
async def ledger_report(
    account_code: str,
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
    counterparty: Optional[str] = Query(None, description="Counterparty INN filter"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    data = await get_account_ledger(tenant_id, account_code, date_from, date_to, counterparty)
    return ok_response("Ledger report", {"report": "ledger", **data})


@limiter.limit("10/minute")
@router.get("/trial-balance")
async def trial_balance_report(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    data = await get_trial_balance(tenant_id, date_from, date_to)
    return ok_response("Trial balance", {"report": "trial_balance", **data})


@limiter.limit("10/minute")
@router.get("/counterparty/{inn}")
async def counterparty_ledger_report(
    inn: str,
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    data = await get_counterparty_ledger(tenant_id, inn, date_from, date_to)
    return ok_response("Counterparty ledger", {"report": "counterparty_ledger", **data})


@limiter.limit("10/minute")
@router.get("/payroll")
async def payroll_ledger_report(
    request: Request,
    employee_id: Optional[str] = Query(None, description="Employee personal tax number"),
    year: Optional[int] = Query(None, ge=1900, le=2100),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    structured_log(
        log,
        logging.INFO,
        "payroll_report_requested",
        tenant_id=tenant_id,
        employee_id=employee_id,
        year=year,
        result="started",
        error_code=None,
    )
    try:
        employee_id, year = normalize_payroll_report_filters(employee_id, year)
    except ValueError as exc:
        structured_log(
            log,
            logging.INFO,
            "payroll_report_rejected",
            tenant_id=tenant_id,
            employee_id=employee_id,
            year=year,
            result="denied",
            error_code="INVALID_FILTER",
        )
        return http_error(422, str(exc), "INVALID_FILTER", {"employee_id": employee_id, "year": year})
    data = await get_payroll_ledger(tenant_id, employee_id, year)
    structured_log(
        log,
        logging.INFO,
        "payroll_report_completed",
        tenant_id=tenant_id,
        employee_id=employee_id,
        year=year,
        result="success",
        error_code=None,
    )
    return ok_response("Payroll ledger", {"report": "payroll_ledger", **data})


@limiter.limit("10/minute")
@router.get("/journal")
async def journal_report(
    request: Request,
    date: Optional[str] = Query(None, description="YYYY-MM-DD — specific date, or omit for latest"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    require_permission(request, "reports:read")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    data = await get_journal_entries(tenant_id, date, limit, offset)
    return ok_response("Journal report", {"report": "journal", **data})


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
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

    conditions = ["tenant_id = %s", "status IN ('posted','simulated_success')"]
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
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

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
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))

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
