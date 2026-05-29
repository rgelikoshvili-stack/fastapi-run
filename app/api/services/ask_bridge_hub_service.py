"""app/api/services/ask_bridge_hub_service.py — Ask Bridge Hub (Task 15).

Natural language query interface for journal data.
Uses a rule-based intent parser (no external AI calls — deterministic, fully testable).

Supported intent types:
  expenses        — "show expenses over 500 GEL this month"
  revenue         — "what was revenue for January"
  unreconciled    — "which drafts are unreconciled"
  drafts_by_status — "show posted drafts"
  balance_summary  — "account balance summary"
  unknown         — fallback

Pipeline:
  question → parse_intent → execute_intent_query → format_answer
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.api.db import get_conn, _q

# ── Intent keywords ────────────────────────────────────────────────────────
_EXPENSE_WORDS  = {"expense", "expenses", "ხარჯი", "ხარჯები", "cost", "costs", "spend"}
_REVENUE_WORDS  = {"revenue", "income", "sales", "შემოსავალი", "გაყიდვები"}
_UNRECON_WORDS  = {"unreconciled", "unmatched", "შეუდარებელი", "not reconciled"}
_STATUS_WORDS   = {"posted", "approved", "drafted", "rejected", "awaiting_cfo", "pending"}
_BALANCE_WORDS  = {"balance", "summary", "ბალანსი", "total", "overview"}

# Amount filter pattern: "over 500", "above 1000", "more than 200"
_AMOUNT_RE   = re.compile(r"(?:over|above|more than|greater than|>)\s*([\d,]+(?:\.\d+)?)", re.I)
_AMOUNT_LT   = re.compile(r"(?:under|below|less than|<)\s*([\d,]+(?:\.\d+)?)", re.I)
# Month pattern: "this month", "January", "2026-01"
_MONTH_RE    = re.compile(
    r"\b(this month|last month|january|february|march|april|may|june|"
    r"july|august|september|october|november|december|\d{4}-\d{2})\b", re.I
)
_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _parse_amount(text: str) -> tuple[float | None, float | None]:
    """Return (min_amount, max_amount) parsed from text."""
    min_amt = max_amt = None
    m = _AMOUNT_RE.search(text)
    if m:
        min_amt = float(m.group(1).replace(",", ""))
    m = _AMOUNT_LT.search(text)
    if m:
        max_amt = float(m.group(1).replace(",", ""))
    return min_amt, max_amt


def _parse_month(text: str) -> str | None:
    """Return YYYY-MM string if a month is found in text, else None."""
    today = date.today()
    m = _MONTH_RE.search(text)
    if not m:
        return None
    token = m.group(1).lower()
    if token == "this month":
        return today.strftime("%Y-%m")
    if token == "last month":
        y, mo = today.year, today.month - 1
        if mo == 0:
            y -= 1; mo = 12
        return f"{y}-{mo:02d}"
    if token in _MONTH_NAMES:
        return f"{today.year}-{_MONTH_NAMES[token]:02d}"
    if re.match(r"\d{4}-\d{2}", token):
        return token
    return None


def parse_intent(question: str) -> dict[str, Any]:
    """Parse a natural language question into a structured intent dict.

    Returns:
        {
          "query_type": str,
          "filters": {"min_amount": float|None, "max_amount": float|None,
                      "month": str|None, "status": str|None},
          "original": str,
        }
    """
    q_lower = question.lower()

    min_amt, max_amt = _parse_amount(q_lower)
    month = _parse_month(q_lower)

    status_filter = None
    for s in _STATUS_WORDS:
        if s in q_lower:
            status_filter = s
            break

    query_type = "unknown"
    if any(w in q_lower for w in _UNRECON_WORDS):
        query_type = "unreconciled"
    elif any(w in q_lower for w in _REVENUE_WORDS):
        query_type = "revenue"
    elif any(w in q_lower for w in _EXPENSE_WORDS):
        query_type = "expenses"
    elif any(w in q_lower for w in _BALANCE_WORDS):
        query_type = "balance_summary"
    elif status_filter:
        query_type = "drafts_by_status"

    return {
        "query_type": query_type,
        "filters": {
            "min_amount": min_amt,
            "max_amount": max_amt,
            "month": month,
            "status": status_filter,
        },
        "original": question,
    }


# ── Query executors ────────────────────────────────────────────────────────

async def _query_expenses(tenant_id: str, filters: dict) -> dict:
    params: list = [tenant_id]
    where = ["tenant_id = $1", "account_code LIKE '7%'",
             "status IN ('posted', 'approved')"]
    if filters.get("min_amount"):
        params.append(filters["min_amount"]); where.append(f"amount >= ${len(params)}")
    if filters.get("max_amount"):
        params.append(filters["max_amount"]); where.append(f"amount <= ${len(params)}")
    if filters.get("month"):
        params.append(filters["month"] + "-01")
        params.append(filters["month"] + "-31")
        where.append(f"created_at::date >= ${len(params)-1}")
        where.append(f"created_at::date <= ${len(params)}")

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT id, description, amount, account_code, status, created_at, partner
                FROM journal_drafts
                WHERE {' AND '.join(where)}
                ORDER BY amount DESC LIMIT 50""",
            *params,
        )
        total = await conn.fetchval(
            f"SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE {' AND '.join(where)}",
            *params,
        )
    return {"rows": [dict(r) for r in rows], "total": round(float(total or 0), 2)}


async def _query_revenue(tenant_id: str, filters: dict) -> dict:
    params: list = [tenant_id]
    where = ["tenant_id = $1", "account_code LIKE '6%'",
             "status IN ('posted', 'approved')"]
    if filters.get("month"):
        params.append(filters["month"] + "-01")
        params.append(filters["month"] + "-31")
        where.append(f"created_at::date >= ${len(params)-1}")
        where.append(f"created_at::date <= ${len(params)}")

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT id, description, amount, account_code, status, created_at, partner
                FROM journal_drafts
                WHERE {' AND '.join(where)}
                ORDER BY amount DESC LIMIT 50""",
            *params,
        )
        total = await conn.fetchval(
            f"SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE {' AND '.join(where)}",
            *params,
        )
    return {"rows": [dict(r) for r in rows], "total": round(float(total or 0), 2)}


async def _query_unreconciled(tenant_id: str, filters: dict) -> dict:
    params: list = [tenant_id]
    where = ["tenant_id = $1", "status IN ('posted','approved','awaiting_cfo')",
             "(reconciled IS NOT TRUE)"]
    if filters.get("min_amount"):
        params.append(filters["min_amount"]); where.append(f"amount >= ${len(params)}")

    async with get_conn() as conn:
        rows = await conn.fetch(
            f"""SELECT id, description, amount, status, created_at, partner
                FROM journal_drafts
                WHERE {' AND '.join(where)}
                ORDER BY created_at ASC LIMIT 50""",
            *params,
        )
        total_amt = await conn.fetchval(
            f"SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE {' AND '.join(where)}",
            *params,
        )
    return {"rows": [dict(r) for r in rows], "total": round(float(total_amt or 0), 2)}


async def _query_by_status(tenant_id: str, filters: dict) -> dict:
    status = filters.get("status", "drafted")
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""SELECT id, description, amount, status, created_at, partner
                 FROM journal_drafts
                 WHERE tenant_id = %s AND status = %s
                 ORDER BY created_at DESC LIMIT 50"""),
            tenant_id, status,
        )
        total = await conn.fetchval(
            _q("SELECT COALESCE(SUM(amount),0) FROM journal_drafts WHERE tenant_id=%s AND status=%s"),
            tenant_id, status,
        )
    return {"rows": [dict(r) for r in rows], "total": round(float(total or 0), 2)}


async def _query_balance_summary(tenant_id: str) -> dict:
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""SELECT account_code,
                         COUNT(*)            AS draft_count,
                         SUM(amount)         AS total_amount
                  FROM journal_drafts
                  WHERE tenant_id = %s AND status IN ('posted','approved')
                  GROUP BY account_code
                  ORDER BY total_amount DESC LIMIT 20"""),
            tenant_id,
        )
    return {"rows": [dict(r) for r in rows]}


# ── Main entry-points ──────────────────────────────────────────────────────

async def execute_intent_query(tenant_id: str, intent: dict) -> dict[str, Any]:
    """Run the DB query for *intent* and return raw results."""
    qt = intent["query_type"]
    f  = intent["filters"]
    if qt == "expenses":
        return await _query_expenses(tenant_id, f)
    if qt == "revenue":
        return await _query_revenue(tenant_id, f)
    if qt == "unreconciled":
        return await _query_unreconciled(tenant_id, f)
    if qt == "drafts_by_status":
        return await _query_by_status(tenant_id, f)
    if qt == "balance_summary":
        return await _query_balance_summary(tenant_id)
    return {"rows": [], "total": 0.0, "note": "Unknown query type — try rephrasing."}


def format_answer(results: dict, intent: dict) -> str:
    """Format query results into a human-readable answer string."""
    qt    = intent["query_type"]
    rows  = results.get("rows", [])
    total = results.get("total", 0.0)
    month = intent["filters"].get("month") or "all time"

    if not rows:
        return f"No records found for '{intent['original']}'."

    if qt == "expenses":
        return (f"Found {len(rows)} expense entries for {month}. "
                f"Total: {total:,.2f} GEL. "
                f"Largest: {rows[0]['description']} — {float(rows[0]['amount']):,.2f} GEL.")
    if qt == "revenue":
        return (f"Found {len(rows)} revenue entries for {month}. "
                f"Total revenue: {total:,.2f} GEL.")
    if qt == "unreconciled":
        return (f"Found {len(rows)} unreconciled drafts. "
                f"Total unreconciled amount: {total:,.2f} GEL.")
    if qt == "drafts_by_status":
        status = intent["filters"].get("status", "?")
        return f"Found {len(rows)} drafts with status '{status}'. Total: {total:,.2f} GEL."
    if qt == "balance_summary":
        return f"Account summary: {len(rows)} accounts with posted/approved transactions."
    return f"Found {len(rows)} records."


async def ask(tenant_id: str, question: str) -> dict[str, Any]:
    """Full pipeline: question → intent → query → formatted answer."""
    intent  = parse_intent(question)
    results = await execute_intent_query(tenant_id, intent)
    answer  = format_answer(results, intent)
    return {
        "question": question,
        "intent":   intent,
        "answer":   answer,
        "results":  results,
    }
