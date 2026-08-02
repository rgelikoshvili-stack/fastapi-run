"""app/api/services/monthly_close_service.py — Monthly Close Cockpit (Phase 6).

Provides:
  - build_close_checklist    — pure: ordered checklist steps definition
  - run_checklist            — async: evaluate each checklist item for a period
  - get_trial_balance_snapshot — async: debit/credit totals by account
  - save_close_signoff       — async: record accountant/CFO sign-off
  - get_close_status         — async: full monthly close status for a period
"""
from __future__ import annotations

from typing import Any

from app.api.db import get_conn, _q

CLOSE_STATUSES = {"draft", "accountant_signed", "cfo_signed", "locked"}

# ---------------------------------------------------------------------------
# Pure checklist definition
# ---------------------------------------------------------------------------

CHECKLIST_ITEMS = [
    {
        "id":    "unposted_drafts",
        "name":  "All transactions posted or rejected",
        "description": "No drafted/pending transactions remain in the period",
    },
    {
        "id":    "reconciliation_rate",
        "name":  "Bank reconciliation ≥ 90%",
        "description": "Posted transactions matched against bank statements",
    },
    {
        "id":    "opening_balances",
        "name":  "Opening balances verified",
        "description": "Opening balance debit/credit are balanced for the period",
    },
    {
        "id":    "payroll_submitted",
        "name":  "Payroll RS.ge submission",
        "description": "Payroll declaration submitted and accepted for the period",
    },
    {
        "id":    "trial_balance",
        "name":  "Trial balance balanced",
        "description": "Total debits equal total credits for posted transactions",
    },
]


def build_close_checklist() -> list[dict]:
    """Return the ordered checklist definition (without evaluation)."""
    return [dict(item, status="pending", detail=None) for item in CHECKLIST_ITEMS]


# ---------------------------------------------------------------------------
# Async checklist evaluators
# ---------------------------------------------------------------------------

async def _check_unposted_drafts(conn, tenant_id: str, month: str) -> dict:
    month_start = f"{month}-01"
    month_end   = f"{month}-31"
    count = await conn.fetchval(
        _q("""
            SELECT COUNT(*) FROM journal_drafts
            WHERE tenant_id = $1
              AND status IN ('drafted', 'awaiting_cfo', 'pending_approval')
              AND date BETWEEN $2 AND $3::date
        """),
        tenant_id, month_start, month_end,
    )
    count = int(count or 0)
    return {
        "status": "ok" if count == 0 else "failed",
        "detail": f"{count} unposted drafts remain" if count else "No unposted drafts",
        "value":  count,
    }


async def _check_reconciliation(conn, tenant_id: str, month: str) -> dict:
    month_start = f"{month}-01"
    month_end   = f"{month}-31"
    row = await conn.fetchrow(
        _q("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE reconciled = TRUE) AS reconciled
            FROM journal_drafts
            WHERE tenant_id = $1
              AND status = 'posted'
              AND date BETWEEN $2 AND $3::date
        """),
        tenant_id, month_start, month_end,
    )
    total = int(row["total"] or 0)
    reconciled = int(row["reconciled"] or 0)
    rate = round(reconciled / total * 100, 1) if total else 100.0
    return {
        "status": "ok" if rate >= 90.0 else ("warning" if rate >= 70.0 else "failed"),
        "detail": f"Reconciliation rate: {rate}% ({reconciled}/{total})",
        "value":  rate,
    }


async def _check_opening_balances(conn, tenant_id: str, month: str) -> dict:
    row = await conn.fetchrow(
        _q("""
            SELECT
                COALESCE(SUM(debit::numeric), 0)  AS total_debit,
                COALESCE(SUM(credit::numeric), 0) AS total_credit
            FROM opening_balances
            WHERE tenant_id = $1
              AND to_char(as_of_date, 'YYYY-MM') = $2
        """),
        tenant_id, month,
    )
    d = float(row["total_debit"] or 0)
    c = float(row["total_credit"] or 0)
    balanced = abs(d - c) < 0.005
    return {
        "status": "ok" if balanced else ("warning" if d == 0 and c == 0 else "failed"),
        "detail": (f"Balanced: {d:.2f} = {c:.2f}" if balanced
                   else f"Unbalanced: debit={d:.2f} credit={c:.2f}"),
        "value":  balanced,
    }


async def _check_payroll_submitted(conn, tenant_id: str, month: str) -> dict:
    row = await conn.fetchrow(
        _q("""
            SELECT status FROM payroll_submissions
            WHERE tenant_id = $1 AND period = $2
            ORDER BY created_at DESC LIMIT 1
        """),
        tenant_id, month,
    )
    if not row:
        return {"status": "warning", "detail": "No payroll submission found", "value": None}
    status = row["status"]
    return {
        "status": "ok" if status in ("accepted", "submitted") else "warning",
        "detail": f"Payroll submission status: {status}",
        "value":  status,
    }


async def _check_trial_balance(conn, tenant_id: str, month: str) -> dict:
    month_start = f"{month}-01"
    month_end   = f"{month}-31"
    row = await conn.fetchrow(
        _q("""
            SELECT
                COALESCE(SUM(
                    (SELECT COALESCE(SUM((l->>'debit')::numeric), 0)
                     FROM jsonb_array_elements(journal_entries) l)
                ), 0) AS total_debit,
                COALESCE(SUM(
                    (SELECT COALESCE(SUM((l->>'credit')::numeric), 0)
                     FROM jsonb_array_elements(journal_entries) l)
                ), 0) AS total_credit
            FROM journal_drafts
            WHERE tenant_id = $1
              AND status = 'posted'
              AND date BETWEEN $2 AND $3::date
        """),
        tenant_id, month_start, month_end,
    )
    d = float(row["total_debit"] or 0)
    c = float(row["total_credit"] or 0)
    balanced = abs(d - c) < 0.01
    return {
        "status": "ok" if balanced else "failed",
        "detail": (f"Balanced: {d:,.2f} = {c:,.2f}" if balanced
                   else f"Unbalanced: debit={d:,.2f} credit={c:,.2f} diff={abs(d-c):,.4f}"),
        "value":  balanced,
    }


# ---------------------------------------------------------------------------
# Public async functions
# ---------------------------------------------------------------------------

async def run_checklist(tenant_id: str, month: str) -> list[dict]:
    """Evaluate all checklist items for *month* (YYYY-MM). Returns enriched list."""
    checkers = {
        "unposted_drafts":   _check_unposted_drafts,
        "reconciliation_rate": _check_reconciliation,
        "opening_balances":  _check_opening_balances,
        "payroll_submitted": _check_payroll_submitted,
        "trial_balance":     _check_trial_balance,
    }
    async with get_conn() as conn:
        results = []
        for item in CHECKLIST_ITEMS:
            checker = checkers.get(item["id"])
            if checker:
                eval_result = await checker(conn, tenant_id, month)
            else:
                eval_result = {"status": "pending", "detail": None, "value": None}
            results.append({**item, **eval_result})
    return results


async def get_trial_balance_snapshot(tenant_id: str, month: str) -> dict[str, Any]:
    """Return debit/credit totals by account for posted transactions in *month*."""
    month_start = f"{month}-01"
    month_end   = f"{month}-31"
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""
                SELECT account_code,
                       SUM((l->>'debit')::numeric)  AS debit,
                       SUM((l->>'credit')::numeric) AS credit
                FROM journal_drafts,
                     jsonb_array_elements(journal_entries) AS l
                WHERE tenant_id = $1
                  AND status = 'posted'
                  AND date BETWEEN $2 AND $3::date
                  AND (l->>'account_code') IS NOT NULL
                GROUP BY account_code
                ORDER BY account_code
            """),
            tenant_id, month_start, month_end,
        )
    lines = [{"account_code": r["account_code"],
              "debit": round(float(r["debit"] or 0), 2),
              "credit": round(float(r["credit"] or 0), 2)} for r in rows]
    total_d = round(sum(l["debit"]  for l in lines), 2)
    total_c = round(sum(l["credit"] for l in lines), 2)
    return {
        "month": month,
        "lines": lines,
        "total_debit":  total_d,
        "total_credit": total_c,
        "balanced":     abs(total_d - total_c) < 0.01,
    }


async def save_close_signoff(
    tenant_id: str,
    month: str,
    signed_by: str,
    role: str,
) -> dict[str, Any]:
    """Record a sign-off step. *role* must be 'accountant' or 'cfo'."""
    if role not in ("accountant", "cfo"):
        raise ValueError("INVALID_ROLE: must be accountant or cfo")
    new_status = "accountant_signed" if role == "accountant" else "cfo_signed"
    async with get_conn() as conn:
        row = await conn.fetchrow(
            _q("""
                INSERT INTO monthly_close_signoffs
                    (tenant_id, month, signed_by, role, status)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (tenant_id, month, role)
                DO UPDATE SET
                    signed_by  = EXCLUDED.signed_by,
                    status     = EXCLUDED.status,
                    signed_at  = NOW()
                RETURNING id, tenant_id, month, signed_by, role, status, signed_at
            """),
            tenant_id, month, signed_by, role, new_status,
        )
    return dict(row)


async def get_close_status(tenant_id: str, month: str) -> dict[str, Any]:
    """Return full monthly close status: checklist + sign-offs."""
    checklist = await run_checklist(tenant_id, month)

    async with get_conn() as conn:
        signoffs = await conn.fetch(
            _q("""
                SELECT role, signed_by, status, signed_at
                FROM monthly_close_signoffs
                WHERE tenant_id = $1 AND month = $2
                ORDER BY signed_at
            """),
            tenant_id, month,
        )

    all_ok = all(item["status"] == "ok" for item in checklist)
    has_accountant = any(r["role"] == "accountant" for r in signoffs)
    has_cfo = any(r["role"] == "cfo" for r in signoffs)

    if has_cfo:
        close_state = "cfo_signed"
    elif has_accountant:
        close_state = "accountant_signed"
    else:
        close_state = "open"

    return {
        "month":       month,
        "close_state": close_state,
        "checklist_ok": all_ok,
        "checklist":   checklist,
        "signoffs":    [dict(r) for r in signoffs],
        "ready_to_lock": all_ok and has_cfo,
    }
