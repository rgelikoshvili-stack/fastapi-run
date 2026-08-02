"""app/api/services/year_close_service.py — Annual Year-End Close.

Provides:
  build_year_close_checklist  — pure: ordered year-end checklist steps
  run_year_checklist          — async: evaluate each item for a fiscal year
  get_year_close_status       — async: full year-end status
  save_year_close_signoff     — async: record CFO / board sign-off
  generate_closing_entries    — async: build year-end journal entry (retain earnings)
  lock_fiscal_year            — async: mark year as locked (no further postings)

Fiscal year format: "YYYY"  (e.g. "2025")
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

YEAR_CLOSE_STATUSES = {"draft", "accountant_signed", "cfo_signed", "board_signed", "locked"}

# Revenue accounts (income): 5xxx, 6xxx
REVENUE_ACCOUNT_PREFIXES = ("5", "6")
# Expense accounts: 7xxx
EXPENSE_ACCOUNT_PREFIXES = ("7",)
# Retained earnings / equity: 4xxx
RETAINED_EARNINGS_ACCOUNT = "4310"

TOLERANCE_GEL = Decimal("0.05")

# ---------------------------------------------------------------------------
# Pure checklist definition
# ---------------------------------------------------------------------------

YEAR_CHECKLIST_ITEMS = [
    {
        "id":    "all_months_closed",
        "name":  "All months signed off",
        "description": "Every month in the fiscal year has CFO sign-off in monthly_close",
    },
    {
        "id":    "no_unposted_drafts",
        "name":  "No unposted transactions",
        "description": "No drafted/pending transactions remain in the fiscal year",
    },
    {
        "id":    "trial_balance_balanced",
        "name":  "Trial balance balanced",
        "description": "Total debits equal total credits for the full year",
    },
    {
        "id":    "depreciation_posted",
        "name":  "Annual depreciation posted",
        "description": "At least one depreciation entry (Dr7xxx Cr1xxx) posted in the year",
    },
    {
        "id":    "payroll_all_submitted",
        "name":  "All payroll periods submitted",
        "description": "Every month in the year has an accepted payroll_submission",
    },
    {
        "id":    "vat_declarations_filed",
        "name":  "VAT declarations filed",
        "description": "Account 3350 has at least one posted entry per month",
    },
]


def build_year_close_checklist() -> list[dict]:
    """Return the ordered year-end checklist (without evaluation)."""
    return [dict(item, status="pending", detail=None, value=None) for item in YEAR_CHECKLIST_ITEMS]


# ---------------------------------------------------------------------------
# Async checklist evaluators
# ---------------------------------------------------------------------------

async def _check_all_months_closed(conn, tenant_id: str, year: str) -> dict:
    try:
        months_ok = 0
        months_total = 12
        for m in range(1, 13):
            month_str = f"{year}-{m:02d}"
            row = await conn.fetchrow(_q("""
                SELECT COUNT(*) AS cnt FROM monthly_close_signoffs
                WHERE tenant_id = %s AND period = %s AND role IN ('cfo', 'CFO')
            """), tenant_id, month_str)
            if row and (row["cnt"] or 0) > 0:
                months_ok += 1
        status = "ok" if months_ok == months_total else "warning" if months_ok >= 6 else "fail"
        return {
            "status": status,
            "detail": f"{months_ok}/{months_total} months with CFO sign-off",
            "value": months_ok,
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e), "value": None}


async def _check_no_unposted_drafts(conn, tenant_id: str, year: str) -> dict:
    try:
        row = await conn.fetchrow(_q("""
            SELECT COUNT(*) AS cnt FROM journal_drafts
            WHERE tenant_id = %s
              AND EXTRACT(YEAR FROM date) = %s
              AND status IN ('drafted', 'pending_approval', 'pending')
        """), tenant_id, int(year))
        cnt = int(row["cnt"] or 0) if row else 0
        return {
            "status": "ok" if cnt == 0 else "fail",
            "detail": f"{cnt} unposted transactions remain",
            "value": cnt,
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e), "value": None}


async def _check_trial_balance(conn, tenant_id: str, year: str) -> dict:
    try:
        row = await conn.fetchrow(_q("""
            SELECT
                COALESCE(SUM(
                    CASE WHEN je->>'type' = 'debit' THEN (je->>'amount')::numeric ELSE 0 END
                ), 0) AS total_debit,
                COALESCE(SUM(
                    CASE WHEN je->>'type' = 'credit' THEN (je->>'amount')::numeric ELSE 0 END
                ), 0) AS total_credit
            FROM journal_drafts,
                 jsonb_array_elements(COALESCE(journal_entries, '[]'::jsonb)) AS je
            WHERE tenant_id = %s
              AND EXTRACT(YEAR FROM date) = %s
              AND status IN ('approved', 'auto_approved', 'posted')
        """), tenant_id, int(year))
        if not row:
            return {"status": "unknown", "detail": "No posted entries found", "value": None}
        debit  = Decimal(str(row["total_debit"]  or 0))
        credit = Decimal(str(row["total_credit"] or 0))
        diff   = abs(debit - credit)
        balanced = diff <= TOLERANCE_GEL
        return {
            "status": "ok" if balanced else "fail",
            "detail": f"Debit={float(debit):.2f} Credit={float(credit):.2f} Diff={float(diff):.2f}",
            "value": {"debit": float(debit), "credit": float(credit), "diff": float(diff)},
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e), "value": None}


async def _check_depreciation_posted(conn, tenant_id: str, year: str) -> dict:
    try:
        row = await conn.fetchrow(_q("""
            SELECT COUNT(*) AS cnt FROM journal_drafts
            WHERE tenant_id = %s
              AND EXTRACT(YEAR FROM date) = %s
              AND status IN ('approved', 'auto_approved', 'posted')
              AND (
                  description ILIKE '%depreciation%'
                  OR description ILIKE '%amortiz%'
                  OR description ILIKE '%ამორტიზ%'
                  OR (debit_account LIKE '7%' AND credit_account LIKE '1%')
              )
        """), tenant_id, int(year))
        cnt = int(row["cnt"] or 0) if row else 0
        return {
            "status": "ok" if cnt > 0 else "warning",
            "detail": f"{cnt} depreciation entries found",
            "value": cnt,
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e), "value": None}


async def _check_payroll_all_submitted(conn, tenant_id: str, year: str) -> dict:
    try:
        rows = await conn.fetch(_q("""
            SELECT DISTINCT TO_CHAR(TO_DATE(period, 'YYYY-MM'), 'YYYY-MM') AS period
            FROM payroll_submissions
            WHERE tenant_id = %s
              AND period LIKE %s
              AND status = 'accepted'
        """), tenant_id, f"{year}-%")
        months_submitted = len(rows)
        status = "ok" if months_submitted >= 12 else "warning" if months_submitted >= 6 else "fail"
        return {
            "status": status,
            "detail": f"{months_submitted}/12 payroll periods accepted",
            "value": months_submitted,
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e), "value": None}


async def _check_vat_declarations(conn, tenant_id: str, year: str) -> dict:
    try:
        rows = await conn.fetch(_q("""
            SELECT DISTINCT TO_CHAR(date, 'YYYY-MM') AS month
            FROM journal_drafts
            WHERE tenant_id = %s
              AND EXTRACT(YEAR FROM date) = %s
              AND status IN ('approved', 'auto_approved', 'posted')
              AND (debit_account = '3350' OR credit_account = '3350')
        """), tenant_id, int(year))
        months_vat = len(rows)
        status = "ok" if months_vat >= 12 else "warning" if months_vat >= 6 else "fail"
        return {
            "status": status,
            "detail": f"VAT entries found in {months_vat}/12 months",
            "value": months_vat,
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e), "value": None}


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------

async def run_year_checklist(tenant_id: str, year: str) -> list[dict]:
    """Evaluate all checklist items for the given fiscal year (YYYY)."""
    async with get_conn() as conn:
        evaluators = [
            ("all_months_closed",       _check_all_months_closed),
            ("no_unposted_drafts",      _check_no_unposted_drafts),
            ("trial_balance_balanced",  _check_trial_balance),
            ("depreciation_posted",     _check_depreciation_posted),
            ("payroll_all_submitted",   _check_payroll_all_submitted),
            ("vat_declarations_filed",  _check_vat_declarations),
        ]
        results = []
        for item in YEAR_CHECKLIST_ITEMS:
            fn = next((f for k, f in evaluators if k == item["id"]), None)
            if fn is None:
                results.append({**item, "status": "unknown", "detail": None, "value": None})
                continue
            evaluation = await fn(conn, tenant_id, year)
            results.append({**item, **evaluation})
    return results


# ---------------------------------------------------------------------------
# Closing journal entries (retained earnings)
# ---------------------------------------------------------------------------

async def generate_closing_entries(tenant_id: str, year: str) -> dict[str, Any]:
    """Compute year-end closing entries: net income → retained earnings.

    Returns a preview of the closing journal entry.
    Does NOT insert — caller decides whether to create the draft.
    """
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            SELECT
                COALESCE(SUM(
                    CASE WHEN (debit_account LIKE '5%%' OR debit_account LIKE '6%%')
                         THEN amount ELSE 0 END
                ), 0) AS revenue_debit,
                COALESCE(SUM(
                    CASE WHEN (credit_account LIKE '5%%' OR credit_account LIKE '6%%')
                         THEN amount ELSE 0 END
                ), 0) AS revenue_credit,
                COALESCE(SUM(
                    CASE WHEN (debit_account LIKE '7%%')
                         THEN amount ELSE 0 END
                ), 0) AS expense_debit,
                COALESCE(SUM(
                    CASE WHEN (credit_account LIKE '7%%')
                         THEN amount ELSE 0 END
                ), 0) AS expense_credit
            FROM journal_drafts
            WHERE tenant_id = %s
              AND EXTRACT(YEAR FROM date) = %s
              AND status IN ('approved', 'auto_approved', 'posted')
        """), tenant_id, int(year))

    if not row:
        return {"ok": False, "error": "No posted entries found for the year"}

    revenue_debit  = float(row["revenue_debit"]  or 0)
    revenue_credit = float(row["revenue_credit"] or 0)
    expense_debit  = float(row["expense_debit"]  or 0)
    expense_credit = float(row["expense_credit"] or 0)

    net_revenue  = revenue_credit - revenue_debit
    net_expense  = expense_debit - expense_credit
    net_income   = round(net_revenue - net_expense, 2)

    if net_income > 0:
        lines = [
            {"account_code": "5000", "debit": net_income, "credit": 0,
             "description": f"Close revenue accounts {year}"},
            {"account_code": RETAINED_EARNINGS_ACCOUNT, "debit": 0, "credit": net_income,
             "description": f"Transfer net income to retained earnings {year}"},
        ]
        description = f"Year-end close {year}: net income {net_income:,.2f} GEL → retained earnings"
    elif net_income < 0:
        loss = abs(net_income)
        lines = [
            {"account_code": RETAINED_EARNINGS_ACCOUNT, "debit": loss, "credit": 0,
             "description": f"Close net loss to retained earnings {year}"},
            {"account_code": "7000", "debit": 0, "credit": loss,
             "description": f"Close expense accounts {year}"},
        ]
        description = f"Year-end close {year}: net loss {loss:,.2f} GEL → retained earnings"
    else:
        lines = []
        description = f"Year-end close {year}: net income = 0, no closing entry needed"

    return {
        "ok": True,
        "year": year,
        "tenant_id": tenant_id,
        "net_revenue": round(net_revenue, 2),
        "net_expense": round(net_expense, 2),
        "net_income": net_income,
        "closing_description": description,
        "closing_lines": lines,
        "retained_earnings_account": RETAINED_EARNINGS_ACCOUNT,
    }


# ---------------------------------------------------------------------------
# Sign-off
# ---------------------------------------------------------------------------

async def save_year_close_signoff(
    tenant_id: str,
    year: str,
    role: str,
    signed_by: str,
    notes: str | None = None,
) -> dict[str, Any]:
    """Record a sign-off for the year-end close."""
    if role not in ("accountant", "cfo", "board"):
        raise ValueError(f"Invalid role: {role}")

    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            INSERT INTO year_close_signoffs
                (tenant_id, year, role, signed_by, notes, signed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (tenant_id, year, role)
            DO UPDATE SET
                signed_by = EXCLUDED.signed_by,
                notes     = EXCLUDED.notes,
                signed_at = EXCLUDED.signed_at
            RETURNING id, tenant_id, year, role, signed_by, signed_at, notes
        """), tenant_id, year, role, signed_by, notes, now)
    return dict(row) if row else {}


# ---------------------------------------------------------------------------
# Full status
# ---------------------------------------------------------------------------

async def get_year_close_status(tenant_id: str, year: str) -> dict[str, Any]:
    """Return complete year-end close status: checklist + signoffs + lock state."""
    checklist = await run_year_checklist(tenant_id, year)

    all_ok = all(item["status"] in ("ok", "warning") for item in checklist)
    critical_ok = all(
        item["status"] == "ok"
        for item in checklist
        if item["id"] in ("no_unposted_drafts", "trial_balance_balanced")
    )

    signoffs: list[dict] = []
    is_locked = False
    try:
        async with get_conn() as conn:
            rows = await conn.fetch(_q("""
                SELECT role, signed_by, signed_at, notes
                FROM year_close_signoffs
                WHERE tenant_id = %s AND year = %s
                ORDER BY signed_at
            """), tenant_id, year)
            signoffs = [dict(r) for r in rows]

            lock_row = await conn.fetchrow(_q("""
                SELECT locked_at FROM year_close_locks
                WHERE tenant_id = %s AND year = %s
            """), tenant_id, year)
            is_locked = lock_row is not None
    except Exception:
        pass

    roles_signed = {s["role"] for s in signoffs}
    ready_to_lock = (
        critical_ok
        and "cfo" in roles_signed
        and not is_locked
    )

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "year": year,
        "checklist": checklist,
        "all_checks_passed": all_ok,
        "critical_checks_passed": critical_ok,
        "signoffs": signoffs,
        "roles_signed": sorted(roles_signed),
        "is_locked": is_locked,
        "ready_to_lock": ready_to_lock,
    }


# ---------------------------------------------------------------------------
# Lock fiscal year
# ---------------------------------------------------------------------------

async def lock_fiscal_year(
    tenant_id: str,
    year: str,
    locked_by: str,
) -> dict[str, Any]:
    """Lock the fiscal year to prevent further postings.

    Requires: CFO sign-off must exist and critical checks must pass.
    """
    status = await get_year_close_status(tenant_id, year)
    if status.get("is_locked"):
        return {"ok": False, "error": f"Fiscal year {year} is already locked"}
    if not status.get("critical_checks_passed"):
        return {
            "ok": False,
            "error": "Critical checks not passed — resolve unposted drafts and trial balance first",
            "checklist": status.get("checklist"),
        }
    if "cfo" not in status.get("roles_signed", []):
        return {"ok": False, "error": "CFO sign-off required before locking fiscal year"}

    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        await conn.execute(_q("""
            INSERT INTO year_close_locks (tenant_id, year, locked_by, locked_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (tenant_id, year) DO NOTHING
        """), tenant_id, year, locked_by, now)

    log.info("fiscal_year_locked tenant=%s year=%s locked_by=%s", tenant_id, year, locked_by)
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "year": year,
        "locked_by": locked_by,
        "locked_at": now.isoformat(),
        "message": f"Fiscal year {year} is now locked",
    }
