"""
Ledger queries — reads from journal_drafts.journal_entries JSONB.
All functions work only with posted drafts (status = 'posted') to show
committed accounting data only.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional
from app.api.db import get_conn, _q
from app.api.services.financial_statements_service import (
    _posted_ledger_reports_enabled,
    _require_tenant_id,
    _assert_no_silent_fallback,
    STANDARD_NET_STATUSES,
)


# ── helpers ────────────────────────────────────────────────────────────────


def _build_trial_balance_posted_ledger_query(
    tenant_id: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> tuple[str, list]:
    """Return (sql, params) for Trial Balance from journal_entry_headers + journal_entry_lines."""
    _require_tenant_id(tenant_id)
    params: list = [tenant_id, list(STANDARD_NET_STATUSES)]
    date_filter = ""
    if date_from:
        params.append(date_from)
        date_filter += f" AND jeh.entry_date >= ${len(params)}"
    if date_to:
        params.append(date_to)
        date_filter += f" AND jeh.entry_date <= ${len(params)}"
    sql = f"""
        SELECT jel.account_code,
               SUM(jel.debit)  AS total_debit,
               SUM(jel.credit) AS total_credit
        FROM journal_entry_lines jel
        JOIN journal_entry_headers jeh ON jeh.id = jel.journal_entry_id
        WHERE jeh.tenant_id = $1
          AND jeh.status = ANY($2)
          {date_filter}
        GROUP BY jel.account_code
        ORDER BY jel.account_code
    """
    _assert_no_silent_fallback(sql)
    return sql, params

def _period_conditions(date_from: Optional[str], date_to: Optional[str], params: list) -> str:
    """Appends date-range filters for journal_drafts.date (text column)."""
    parts = []
    if date_from:
        parts.append("(jd.date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND jd.date::date >= %s)")
        params.append(date_from)
    if date_to:
        parts.append("(jd.date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND jd.date::date <= %s)")
        params.append(date_to)
    return (" AND " + " AND ".join(parts)) if parts else ""


# ── 1. Account Ledger ───────────────────────────────────────────────────────

async def get_account_ledger(
    tenant_id: str,
    account_code: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    counterparty_inn: Optional[str] = None,
) -> dict:
    """
    Returns all debit/credit movements for one account_code with running balance.
    Opening balance is computed from posted entries before date_from when provided.
    """
    params: list = [tenant_id, account_code, account_code]
    period = _period_conditions(date_from, date_to, params)
    counterparty_filter = ""
    if counterparty_inn:
        counterparty_filter = " AND jd.counterparty_inn = %s"
        params.append(counterparty_inn)

    opening = Decimal("0")
    if date_from:
        opening_params: list = [tenant_id, account_code, account_code, date_from]
        opening_counterparty = ""
        if counterparty_inn:
            opening_counterparty = " AND jd.counterparty_inn = %s"
            opening_params.append(counterparty_inn)
        opening_sql = _q(f"""
            SELECT
                entry->>'dr' AS dr,
                entry->>'cr' AS cr,
                COALESCE(SUM((entry->>'amount')::numeric), 0) AS total
            FROM journal_drafts jd
            CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
            WHERE jd.tenant_id = %s
              AND jd.status = 'posted'
              AND (entry->>'dr' = %s OR entry->>'cr' = %s)
              AND jd.date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
              AND jd.date::date < %s
              {opening_counterparty}
            GROUP BY entry->>'dr', entry->>'cr'
        """)
        async with get_conn() as conn:
            opening_rows = await conn.fetch(opening_sql, *opening_params)
        for r in opening_rows:
            amt = Decimal(str(r["total"] or 0))
            opening += amt if r["dr"] == account_code else -amt

    sql = _q(f"""
        SELECT
            jd.id          AS draft_id,
            jd.date,
            jd.description,
            jd.counterparty_name,
            entry->>'dr'                   AS dr,
            entry->>'cr'                   AS cr,
            (entry->>'amount')::numeric    AS amount,
            entry->>'note'                 AS note
        FROM journal_drafts jd
        CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          AND (entry->>'dr' = %s OR entry->>'cr' = %s)
          {period}
          {counterparty_filter}
        ORDER BY
            CASE WHEN jd.date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                 THEN jd.date::date ELSE jd.created_at::date END,
            jd.id
    """)

    async with get_conn() as conn:
        rows = await conn.fetch(sql, *params)

    lines = []
    running = opening
    total_dr = Decimal("0")
    total_cr = Decimal("0")

    for r in rows:
        amt = Decimal(str(r["amount"] or 0))
        is_dr = r["dr"] == account_code
        dr_amt = amt if is_dr else Decimal("0")
        cr_amt = amt if not is_dr else Decimal("0")
        running += dr_amt - cr_amt
        total_dr += dr_amt
        total_cr += cr_amt
        lines.append({
            "draft_id": r["draft_id"],
            "date": r["date"],
            "description": r["description"] or r["note"],
            "counterparty": r["counterparty_name"],
            "dr_account": r["dr"],
            "cr_account": r["cr"],
            "debit": float(dr_amt),
            "credit": float(cr_amt),
            "balance": float(running),
        })

    return {
        "account_code": account_code,
        "counterparty_inn": counterparty_inn,
        "date_from": date_from,
        "date_to": date_to,
        "opening_balance": float(opening),
        "total_debit": float(total_dr),
        "total_credit": float(total_cr),
        "closing_balance": float(running),
        "lines": lines,
        "count": len(lines),
    }


# ── 2. Trial Balance ────────────────────────────────────────────────────────

async def _get_trial_balance_from_posted_ledger(
    tenant_id: str,
    date_from: Optional[str],
    date_to: Optional[str],
) -> dict:
    """Execute posted-ledger Trial Balance query; fail closed if tables unavailable."""
    _require_tenant_id(tenant_id)
    sql, params = _build_trial_balance_posted_ledger_query(tenant_id, date_from, date_to)
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(sql, *params)
    except Exception as e:
        return {
            "error": "POSTED_LEDGER_UNAVAILABLE",
            "detail": str(e),
            "date_from": date_from,
            "date_to": date_to,
            "accounts": [],
            "count": 0,
        }

    items = []
    for row in rows:
        dr = float(row["total_debit"] or 0)
        cr = float(row["total_credit"] or 0)
        items.append({
            "account_code": row["account_code"],
            "opening_balance": 0.0,
            "debit_turnover": round(dr, 2),
            "credit_turnover": round(cr, 2),
            "closing_balance": round(dr - cr, 2),
            "debit": round(dr, 2),
            "credit": round(cr, 2),
            "net": round(dr - cr, 2),
        })

    grand_dr = round(sum(i["debit_turnover"] for i in items), 2)
    grand_cr = round(sum(i["credit_turnover"] for i in items), 2)
    return {
        "source": "posted_ledger",
        "date_from": date_from,
        "date_to": date_to,
        "total_debit": grand_dr,
        "total_credit": grand_cr,
        "balanced": grand_dr == grand_cr,
        "opening_total": 0.0,
        "closing_total": round(grand_dr - grand_cr, 2),
        "accounts": items,
        "count": len(items),
    }


async def get_trial_balance(
    tenant_id: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """
    Aggregates posted journal_entries into a trial balance grouped by account_code.
    Rows include opening balance, period debit/credit turnover, and closing balance.
    """
    if _posted_ledger_reports_enabled():
        return await _get_trial_balance_from_posted_ledger(tenant_id, date_from, date_to)

    where_params: list = [tenant_id]
    date_to_filter = ""
    if date_to:
        date_to_filter = " AND jd.date::date <= %s"
        where_params.append(date_to)

    sql = _q(f"""
        SELECT
            entry->>'dr'                    AS account_code,
            'debit'                         AS side,
            CASE
                WHEN %s::date IS NOT NULL AND jd.date::date < %s::date
                THEN 'opening'
                ELSE 'period'
            END                              AS bucket,
            SUM((entry->>'amount')::numeric) AS total
        FROM journal_drafts jd
        CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          AND jd.date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
          {date_to_filter}
        GROUP BY entry->>'dr'
               , CASE
                    WHEN %s::date IS NOT NULL AND jd.date::date < %s::date
                    THEN 'opening'
                    ELSE 'period'
                 END

        UNION ALL

        SELECT
            entry->>'cr'                    AS account_code,
            'credit'                        AS side,
            CASE
                WHEN %s::date IS NOT NULL AND jd.date::date < %s::date
                THEN 'opening'
                ELSE 'period'
            END                              AS bucket,
            SUM((entry->>'amount')::numeric) AS total
        FROM journal_drafts jd
        CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          AND jd.date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
          {date_to_filter}
        GROUP BY entry->>'cr'
               , CASE
                    WHEN %s::date IS NOT NULL AND jd.date::date < %s::date
                    THEN 'opening'
                    ELSE 'period'
                 END
        ORDER BY account_code, side
    """)

    branch_params = [date_from, date_from, *where_params, date_from, date_from]
    params_full = branch_params + branch_params

    async with get_conn() as conn:
        rows = await conn.fetch(sql, *params_full)

    accounts: dict[str, dict] = {}
    for r in rows:
        code = r["account_code"] or ""
        if code not in accounts:
            accounts[code] = {
                "account_code": code,
                "opening_debit": 0.0,
                "opening_credit": 0.0,
                "debit_turnover": 0.0,
                "credit_turnover": 0.0,
            }
        bucket = "opening" if r["bucket"] == "opening" else "period"
        if bucket == "opening" and r["side"] == "debit":
            accounts[code]["opening_debit"] += float(r["total"] or 0)
        elif bucket == "opening":
            accounts[code]["opening_credit"] += float(r["total"] or 0)
        elif r["side"] == "debit":
            accounts[code]["debit_turnover"] += float(r["total"] or 0)
        else:
            accounts[code]["credit_turnover"] += float(r["total"] or 0)

    items = []
    for raw in sorted(accounts.values(), key=lambda x: x["account_code"]):
        opening_balance = raw["opening_debit"] - raw["opening_credit"]
        closing_balance = opening_balance + raw["debit_turnover"] - raw["credit_turnover"]
        items.append({
            "account_code": raw["account_code"],
            "opening_balance": round(opening_balance, 2),
            "debit_turnover": round(raw["debit_turnover"], 2),
            "credit_turnover": round(raw["credit_turnover"], 2),
            "closing_balance": round(closing_balance, 2),
            "debit": round(raw["debit_turnover"], 2),
            "credit": round(raw["credit_turnover"], 2),
            "net": round(closing_balance, 2),
        })

    grand_dr = sum(i["debit_turnover"] for i in items)
    grand_cr = sum(i["credit_turnover"] for i in items)
    opening_total = sum(i["opening_balance"] for i in items)
    closing_total = sum(i["closing_balance"] for i in items)

    return {
        "date_from": date_from,
        "date_to": date_to,
        "total_debit": round(grand_dr, 2),
        "total_credit": round(grand_cr, 2),
        "balanced": round(grand_dr, 2) == round(grand_cr, 2),
        "opening_total": round(opening_total, 2),
        "closing_total": round(closing_total, 2),
        "accounts": items,
        "count": len(items),
    }


# ── 3. Counterparty Ledger ──────────────────────────────────────────────────

async def get_counterparty_ledger(
    tenant_id: str,
    counterparty_inn: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """
    All posted journal drafts for a specific counterparty (by INN/tax_id).
    Returns document-level lines (not entry-level) with total amounts.
    """
    params: list = [tenant_id, counterparty_inn]
    period = _period_conditions(date_from, date_to, params)

    sql = _q(f"""
        SELECT
            jd.id,
            jd.date,
            jd.description,
            jd.counterparty_inn,
            jd.counterparty_name,
            jd.amount,
            jd.account_code,
            jd.reason,
            jd.status,
            jd.journal_entries
        FROM journal_drafts jd
        WHERE jd.tenant_id = %s
          AND jd.counterparty_inn = %s
          AND jd.status = 'posted'
          {period}
        ORDER BY
            CASE WHEN jd.date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                 THEN jd.date::date ELSE jd.created_at::date END,
            jd.id
    """)

    async with get_conn() as conn:
        rows = await conn.fetch(sql, *params)

    lines = []
    total = Decimal("0")
    for r in rows:
        amt = Decimal(str(r["amount"] or 0))
        total += amt
        lines.append({
            "id": r["id"],
            "date": r["date"],
            "description": r["description"],
            "counterparty_inn": r["counterparty_inn"],
            "counterparty_name": r["counterparty_name"],
            "amount": float(amt),
            "account_code": r["account_code"],
            "reason": r["reason"],
            "journal_entries": r["journal_entries"] or [],
        })

    return {
        "counterparty_inn": counterparty_inn,
        "date_from": date_from,
        "date_to": date_to,
        "total_amount": float(total),
        "count": len(lines),
        "lines": lines,
    }


# ── 4. Payroll Ledger ───────────────────────────────────────────────────────

_PAYROLL_ACCOUNTS = ("7110", "7120", "7210", "7130", "3320", "3330", "3335", "3370", "3380", "2120")

async def get_payroll_ledger(
    tenant_id: str,
    employee_id: Optional[str] = None,
    year: Optional[int] = None,
) -> dict:
    """
    Payroll-related journal entries (accounts 7110-7130 wages, 3370/3380 payables).
    employee_id maps to counterparty_inn in journal_drafts (personal tax number).
    """
    params: list = [tenant_id, list(_PAYROLL_ACCOUNTS)]
    year_filter = ""
    if year:
        year_filter = " AND (jd.date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' AND EXTRACT(YEAR FROM jd.date::date) = %s)"
        params.append(year)

    emp_filter = ""
    if employee_id:
        emp_filter = " AND jd.counterparty_inn = %s"
        params.append(employee_id)

    sql = _q(f"""
        SELECT
            jd.id,
            jd.date,
            jd.description,
            jd.counterparty_inn  AS employee_inn,
            jd.counterparty_name AS employee_name,
            entry->>'dr'                    AS dr,
            entry->>'cr'                    AS cr,
            (entry->>'amount')::numeric     AS amount,
            entry->>'note'                  AS note
        FROM journal_drafts jd
        CROSS JOIN LATERAL jsonb_array_elements(jd.journal_entries) AS entry
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          AND (entry->>'dr' = ANY(%s) OR entry->>'cr' = ANY(%s))
          {year_filter}
          {emp_filter}
        ORDER BY
            CASE WHEN jd.date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                 THEN jd.date::date ELSE jd.created_at::date END,
            jd.id
    """)

    # ANY($n) appears twice — add the payroll accounts list a second time
    params_full = [params[0], params[1], params[1]] + params[2:]

    async with get_conn() as conn:
        rows = await conn.fetch(sql, *params_full)

    lines = []
    total_wages = Decimal("0")
    for r in rows:
        amt = Decimal(str(r["amount"] or 0))
        if r["dr"] in _PAYROLL_ACCOUNTS:
            total_wages += amt
        lines.append({
            "draft_id": r["id"],
            "date": r["date"],
            "employee_inn": r["employee_inn"],
            "employee_name": r["employee_name"],
            "dr": r["dr"],
            "cr": r["cr"],
            "amount": float(amt),
            "note": r["note"] or r["description"],
        })

    return {
        "employee_id": employee_id,
        "year": year,
        "total_wages": float(total_wages),
        "count": len(lines),
        "lines": lines,
    }


# ── 5. Journal for a specific date ─────────────────────────────────────────

async def get_journal_entries(
    tenant_id: str,
    date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    Returns all posted journal drafts (with expanded entries) for a given date.
    If date is None, returns the most recent posted drafts.
    """
    params: list = [tenant_id]
    date_filter = ""
    if date:
        date_filter = " AND jd.date = %s"
        params.append(date)

    count_params = list(params)
    params += [limit, offset]

    sql = _q(f"""
        SELECT
            jd.id,
            jd.date,
            jd.description,
            jd.partner,
            jd.counterparty_inn,
            jd.counterparty_name,
            jd.amount,
            jd.account_code,
            jd.debit_account,
            jd.credit_account,
            jd.reason,
            jd.status,
            jd.journal_entries
        FROM journal_drafts jd
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          {date_filter}
        ORDER BY
            CASE WHEN jd.date ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}'
                 THEN jd.date::date ELSE jd.created_at::date END DESC,
            jd.id DESC
        LIMIT %s OFFSET %s
    """)

    count_sql = _q(f"""
        SELECT COUNT(*) AS total FROM journal_drafts jd
        WHERE jd.tenant_id = %s
          AND jd.status = 'posted'
          {date_filter}
    """)

    async with get_conn() as conn:
        total_row = await conn.fetchrow(count_sql, *count_params)
        total = total_row["total"] if total_row else 0
        rows = await conn.fetch(sql, *params)

    entries = []
    for r in rows:
        entries.append({
            "id": r["id"],
            "date": r["date"],
            "description": r["description"],
            "partner": r["partner"],
            "counterparty_inn": r["counterparty_inn"],
            "counterparty_name": r["counterparty_name"],
            "amount": float(r["amount"] or 0),
            "account_code": r["account_code"],
            "debit_account": r["debit_account"],
            "credit_account": r["credit_account"],
            "reason": r["reason"],
            "status": r["status"],
            "entries": r["journal_entries"] or [],
        })

    return {
        "date": date,
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": entries,
    }
