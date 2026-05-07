"""
app/api/services/ai_tool_registry.py
Bridge Hub — AI Tool Registry

8 structured tools available to the AI Orchestrator.
All tools return {approval_required, preview, ...} — never execute.
All queries are tenant-scoped.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.api.db import get_conn, _q

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Tool registry — maps tool_name → function
# ─────────────────────────────────────────────────────────────

TOOL_DESCRIPTIONS = {
    "explain_draft":            "Fetch and explain a specific journal draft in detail",
    "show_risks":               "Show high-risk drafts: low confidence, high amount, missing fields",
    "show_pending_tasks":       "List all pending approval tasks with priority",
    "financial_summary":        "P&L, revenue, expenses, profit summary for the tenant",
    "tax_summary":              "VAT/PIT/CIT payable summary from approved entries",
    "search_documents":         "Full-text search across drafts, invoices, waybills by keyword",
    "prepare_approval_preview": "Prepare an approval preview for a draft (human must confirm)",
    "prepare_posting_preview":  "Prepare a posting preview to Balance.ge or 1C (human must confirm)",
}

TOOL_NAMES = list(TOOL_DESCRIPTIONS)


async def run_tool(tool_name: str, params: dict, tenant_id: str) -> dict:
    """
    Dispatch a tool call. Returns structured result.
    Never executes write operations.
    """
    fn = _TOOL_MAP.get(tool_name)
    if not fn:
        return {"error": f"Unknown tool: {tool_name}", "available": list(TOOL_DESCRIPTIONS)}
    try:
        return await fn(params, tenant_id)
    except Exception as e:
        log.error("tool %s failed: %s", tool_name, e)
        return {"error": str(e), "tool": tool_name}


# ─────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────

async def _explain_draft(params: dict, tenant_id: str) -> dict:
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"error": "draft_id required"}

    async with get_conn() as conn:
        row = await conn.fetchrow(_q("""
            SELECT id, description, amount, partner, account_code,
                   debit_account, credit_account, status, confidence,
                   source_type, date, created_at, reason
            FROM journal_drafts
            WHERE id = %s AND tenant_id = %s
        """), int(draft_id), tenant_id)

    if not row:
        return {"found": False, "message": f"Draft #{draft_id} ვერ მოიძებნა სისტემაში"}

    d = _safe(row)
    risk_flags = []
    conf = float(d.get("confidence") or 0)
    amt = float(d.get("amount") or 0)
    if conf < 0.75:
        risk_flags.append(f"დაბალი confidence: {conf:.0%}")
    if amt >= 50_000:
        risk_flags.append(f"მაღალი თანხა: {amt:,.0f} GEL")
    if not d.get("debit_account") or not d.get("credit_account"):
        risk_flags.append("Dr/Cr ანგარიში არ არის")

    return {
        "found": True,
        "approval_required": False,
        "draft": d,
        "risk_flags": risk_flags,
        "explanation": {
            "what": d.get("description"),
            "who": d.get("partner") or "უცნობი პარტნიორი",
            "amount": f"{amt:,.2f} GEL",
            "accounts": f"Dr {d.get('debit_account')} / Cr {d.get('credit_account')}",
            "status": d.get("status"),
            "confidence": f"{conf:.0%}",
            "source": d.get("source_type"),
            "date": str(d.get("date") or d.get("created_at") or ""),
        },
    }


async def _show_risks(params: dict, tenant_id: str) -> dict:
    limit = int(params.get("limit", 10))
    async with get_conn() as conn:
        rows = [_safe(r) for r in await conn.fetch(_q("""
            SELECT id, description, amount, partner, status, confidence,
                   debit_account, credit_account, created_at
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('pending_approval', 'drafted')
              AND (
                  confidence < 0.75
                  OR amount >= 50000
                  OR debit_account IS NULL
                  OR credit_account IS NULL
              )
            ORDER BY
                CASE WHEN confidence < 0.75 THEN 0 ELSE 1 END,
                amount DESC
            LIMIT %s
        """), tenant_id, limit)]

    risks = []
    for r in rows:
        flags = []
        conf = float(r.get("confidence") or 0)
        amt = float(r.get("amount") or 0)
        if conf < 0.75:
            flags.append(f"confidence {conf:.0%}")
        if amt >= 50_000:
            flags.append(f"თანხა {amt:,.0f} GEL")
        if not r.get("debit_account") or not r.get("credit_account"):
            flags.append("Dr/Cr აკლია")
        risks.append({**r, "risk_flags": flags})

    return {
        "approval_required": False,
        "risk_count": len(risks),
        "risks": risks,
        "summary": f"{len(risks)} სარისკო draft მოიძებნა",
    }


async def _show_pending_tasks(params: dict, tenant_id: str) -> dict:
    limit = int(params.get("limit", 20))
    async with get_conn() as conn:
        rows = [_safe(r) for r in await conn.fetch(_q("""
            SELECT id, description, amount, partner, status,
                   confidence, created_at, source_type
            FROM journal_drafts
            WHERE tenant_id = %s
              AND status IN ('pending_approval', 'drafted', 'pending_human_review')
            ORDER BY
                CASE WHEN status='pending_human_review' THEN 0
                     WHEN confidence < 0.75 THEN 1
                     ELSE 2 END,
                created_at ASC
            LIMIT %s
        """), tenant_id, limit)]

        total = await conn.fetchval(_q(
            "SELECT COUNT(*) FROM journal_drafts "
            "WHERE tenant_id=%s AND status IN ('pending_approval','drafted','pending_human_review')"
        ), tenant_id) or 0

    return {
        "approval_required": False,
        "total_pending": int(total),
        "shown": len(rows),
        "tasks": rows,
        "summary": f"სულ {total} pending task",
    }


async def _financial_summary(params: dict, tenant_id: str) -> dict:
    async with get_conn() as conn:
        row = _safe(await conn.fetchrow(_q("""
            SELECT
                COUNT(*) as total_drafts,
                COUNT(CASE WHEN status IN ('approved','auto_approved') THEN 1 END) as approved,
                COUNT(CASE WHEN status='pending_approval' THEN 1 END) as pending,
                COUNT(CASE WHEN status='rejected' THEN 1 END) as rejected,
                COALESCE(SUM(CASE WHEN credit_account LIKE '6%%'
                    AND status IN ('approved','auto_approved') THEN amount ELSE 0 END), 0) as revenue,
                COALESCE(SUM(CASE WHEN debit_account  LIKE '7%%'
                    AND status IN ('approved','auto_approved') THEN amount ELSE 0 END), 0) as expenses,
                COALESCE(AVG(confidence), 0) as avg_confidence
            FROM journal_drafts
            WHERE tenant_id = %s
        """), tenant_id))

        banks = [_safe(r) for r in await conn.fetch(_q(
            "SELECT name, balance, currency FROM bank_accounts "
            "WHERE tenant_id=%s ORDER BY balance DESC LIMIT 5"
        ), tenant_id)]

    rev = float(row.get("revenue") or 0)
    exp = float(row.get("expenses") or 0)
    profit = rev - exp

    return {
        "approval_required": False,
        "preview": {
            "revenue":         f"{rev:,.2f} GEL",
            "expenses":        f"{exp:,.2f} GEL",
            "profit":          f"{profit:,.2f} GEL",
            "margin":          f"{profit/rev*100:.1f}%" if rev > 0 else "N/A",
            "total_drafts":    int(row.get("total_drafts") or 0),
            "approved":        int(row.get("approved") or 0),
            "pending":         int(row.get("pending") or 0),
            "rejected":        int(row.get("rejected") or 0),
            "avg_confidence":  f"{float(row.get('avg_confidence') or 0):.0%}",
            "bank_accounts":   banks,
        },
    }


async def _tax_summary(params: dict, tenant_id: str) -> dict:
    async with get_conn() as conn:
        row = _safe(await conn.fetchrow(_q("""
            SELECT
                COALESCE(SUM(CASE WHEN credit_account='3310' THEN amount ELSE 0 END),0) as vat_payable,
                COALESCE(SUM(CASE WHEN credit_account='3320' THEN amount ELSE 0 END),0) as pit_payable,
                COALESCE(SUM(CASE WHEN credit_account='3340' THEN amount ELSE 0 END),0) as cit_payable,
                COALESCE(SUM(CASE WHEN credit_account='3330' THEN amount ELSE 0 END),0) as payg_payable,
                COALESCE(SUM(CASE WHEN credit_account='3350' THEN amount ELSE 0 END),0) as withholding_payable
            FROM journal_drafts
            WHERE tenant_id = %s AND status IN ('approved','auto_approved')
        """), tenant_id))

    return {
        "approval_required": False,
        "preview": {
            "vat_payable":         f"{float(row.get('vat_payable') or 0):,.2f} GEL",
            "pit_payable":         f"{float(row.get('pit_payable') or 0):,.2f} GEL",
            "cit_payable":         f"{float(row.get('cit_payable') or 0):,.2f} GEL",
            "payg_payable":        f"{float(row.get('payg_payable') or 0):,.2f} GEL",
            "withholding_payable": f"{float(row.get('withholding_payable') or 0):,.2f} GEL",
            "note":                "მონაცემები: journal_drafts approved/auto_approved entries",
        },
    }


async def _search_documents(params: dict, tenant_id: str) -> dict:
    query = (params.get("query") or "").strip()
    if not query:
        return {"error": "query required"}
    limit = int(params.get("limit", 10))
    like = f"%{query}%"
    results = []

    async with get_conn() as conn:
        try:
            rows = await conn.fetch(_q("""
                SELECT id, description, amount, partner, status, 'draft' as source_table
                FROM journal_drafts
                WHERE tenant_id = %s AND (description ILIKE %s OR partner ILIKE %s)
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, like, like, limit)
            results += [_safe(r) for r in rows]
        except Exception as e:
            log.debug("search drafts: %s", e)

        try:
            rows = await conn.fetch(_q("""
                SELECT id, number as description, partner, total as amount,
                       status, 'invoice' as source_table
                FROM invoices
                WHERE tenant_id = %s AND (partner ILIKE %s OR number ILIKE %s)
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, like, like, limit)
            results += [_safe(r) for r in rows]
        except Exception as e:
            log.debug("search invoices: %s", e)

        try:
            rows = await conn.fetch(_q("""
                SELECT id, invoice_number as description, partner_name as partner,
                       total_amount as amount, status, 'outgoing_invoice' as source_table
                FROM outgoing_invoices
                WHERE tenant_id = %s AND (partner_name ILIKE %s OR invoice_number ILIKE %s)
                ORDER BY issue_date DESC LIMIT %s
            """), tenant_id, like, like, limit)
            results += [_safe(r) for r in rows]
        except Exception as e:
            log.debug("search outgoing: %s", e)

    return {
        "approval_required": False,
        "query": query,
        "total_found": len(results),
        "results": results[:limit],
        "summary": f"'{query}'-ზე {len(results)} შედეგი",
    }


async def _prepare_approval_preview(params: dict, tenant_id: str) -> dict:
    draft_id = params.get("draft_id")
    if not draft_id:
        return {"error": "draft_id required"}

    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT id, description, amount, partner, status, confidence, "
            "debit_account, credit_account, account_code "
            "FROM journal_drafts WHERE id=%s AND tenant_id=%s"
        ), int(draft_id), tenant_id)

    if not row:
        return {"found": False, "message": f"Draft #{draft_id} ვერ მოიძებნა"}

    d = _safe(row)
    return {
        "approval_required": True,
        "found": True,
        "preview": {
            "draft_id":       d["id"],
            "description":    d["description"],
            "amount":         f"{float(d.get('amount') or 0):,.2f} GEL",
            "partner":        d.get("partner"),
            "current_status": d["status"],
            "new_status":     "approved",
            "dr_account":     d.get("debit_account"),
            "cr_account":     d.get("credit_account"),
            "confidence":     f"{float(d.get('confidence') or 0):.0%}",
        },
        "confirm_url":    f"/api/approval/approve/{draft_id}",
        "confirm_method": "POST",
        "warning":        "ადამიანის დადასტურება საჭიროა. AI ვერ ასრულებს.",
    }


async def _prepare_posting_preview(params: dict, tenant_id: str) -> dict:
    draft_id = params.get("draft_id")
    target = params.get("target", "balance_ge")
    if not draft_id:
        return {"error": "draft_id required"}

    async with get_conn() as conn:
        row = await conn.fetchrow(_q(
            "SELECT id, description, amount, partner, status, confidence, "
            "debit_account, credit_account, date "
            "FROM journal_drafts WHERE id=%s AND tenant_id=%s"
        ), int(draft_id), tenant_id)

    if not row:
        return {"found": False, "message": f"Draft #{draft_id} ვერ მოიძებნა"}

    d = _safe(row)
    _target_urls = {
        "balance_ge": "/api/balance-ge/post-journals",
        "1c":         "/api/1c/post",
    }

    return {
        "approval_required": True,
        "found": True,
        "target": target,
        "preview": {
            "draft_id":     d["id"],
            "description":  d["description"],
            "amount":       f"{float(d.get('amount') or 0):,.2f} GEL",
            "partner":      d.get("partner"),
            "date":         str(d.get("date") or ""),
            "dr_account":   d.get("debit_account"),
            "cr_account":   d.get("credit_account"),
            "status":       d["status"],
            "ready":        d["status"] in ("approved", "auto_approved"),
        },
        "confirm_url":    _target_urls.get(target, "/api/balance-ge/post-journals"),
        "confirm_method": "POST",
        "warning":        f"{target} posting — ადამიანის დადასტურება საჭიროა. AI ვერ ასრულებს.",
    }


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _safe(row) -> dict:
    if row is None:
        return {}
    d = dict(row)
    import decimal
    for k, v in d.items():
        if isinstance(v, decimal.Decimal):
            d[k] = float(v)
        elif hasattr(v, "isoformat"):
            d[k] = str(v)
    return d


_TOOL_MAP = {
    "explain_draft":            _explain_draft,
    "show_risks":               _show_risks,
    "show_pending_tasks":       _show_pending_tasks,
    "financial_summary":        _financial_summary,
    "tax_summary":              _tax_summary,
    "search_documents":         _search_documents,
    "prepare_approval_preview": _prepare_approval_preview,
    "prepare_posting_preview":  _prepare_posting_preview,
}
