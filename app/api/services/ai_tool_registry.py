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
    "explain_draft":              "Fetch and explain a specific journal draft in detail",
    "show_risks":                 "Show high-risk drafts: low confidence, high amount, missing fields",
    "show_pending_tasks":         "List all pending approval tasks with priority",
    "financial_summary":          "P&L, revenue, expenses, profit summary for the tenant",
    "tax_summary":                "VAT/PIT/CIT payable summary from approved entries",
    "search_documents":           "Full-text search across drafts, invoices, waybills, tax invoices, evidence by keyword",
    "prepare_approval_preview":   "Prepare an approval preview for a draft (human must confirm)",
    "prepare_posting_preview":    "Prepare a posting preview to Balance.ge or 1C (human must confirm)",
    "get_rsge_document_status":   "Look up a waybill or tax invoice by number — returns redacted summary",
    "get_triangle_match_status":  "Get 3-way match status for waybill + tax invoice + commercial invoice",
    "get_accounting_risk_summary": "Risk summary: missing docs, duplicates, FX missing, period lock, VAT mismatch",
    "get_bank_transactions":       "Search bank statement transactions: by partner, amount range, date range, or unreconciled only",
    "get_payment_status":          "Check payment status for an invoice or waybill: paid, partial, unpaid, overpaid, with matched bank transactions",
    # Sprint 2 — Cross-reference tools
    "get_contracts":              "Search contracts by party name, type, or status; shows value, dates, payment terms, and overdue milestones",
    "get_payroll_status":         "Check RS.ge payroll submission status for a period (YYYY-MM): draft/submitted/accepted/rejected",
    "get_posting_log":            "Look up ERP posting history for a journal draft: target system, status, errors, timestamps",
    "get_monthly_close_status":   "Run the monthly close checklist for a period: unposted drafts, reconciliation, trial balance, payroll, opening balances",
    "get_rsge_documents":         "List RS.ge-imported waybills and tax invoices; filter by seller_inn, buyer_inn, or status",
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
    """P0-5: Extended search across all document types including RS.ge documents."""
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

        # P0-5: waybills (ზედნადები)
        try:
            rows = await conn.fetch(_q("""
                SELECT id, waybill_number as description,
                       seller_name as partner, total_amount as amount,
                       status, 'waybill' as source_table
                FROM waybills
                WHERE tenant_id = %s
                  AND (seller_name ILIKE %s OR buyer_name ILIKE %s OR waybill_number ILIKE %s)
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, like, like, like, limit)
            results += [_safe(r) for r in rows]
        except Exception as e:
            log.debug("search waybills: %s", e)

        # P0-5: tax invoices (სფ)
        try:
            rows = await conn.fetch(_q("""
                SELECT id, invoice_number as description,
                       seller_name as partner, total_amount as amount,
                       status, 'tax_invoice' as source_table
                FROM tax_invoices
                WHERE tenant_id = %s
                  AND (seller_name ILIKE %s OR buyer_name ILIKE %s OR invoice_number ILIKE %s)
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, like, like, like, limit)
            results += [_safe(r) for r in rows]
        except Exception as e:
            log.debug("search tax_invoices: %s", e)

        # P0-5: commercial invoices
        try:
            rows = await conn.fetch(_q("""
                SELECT id, invoice_number as description,
                       seller_name as partner, total_amount as amount,
                       status, 'commercial_invoice' as source_table
                FROM commercial_invoices
                WHERE tenant_id = %s
                  AND (seller_name ILIKE %s OR buyer_name ILIKE %s OR invoice_number ILIKE %s)
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, like, like, like, limit)
            results += [_safe(r) for r in rows]
        except Exception as e:
            log.debug("search commercial_invoices: %s", e)

        # P0-5: evidence bundles
        try:
            rows = await conn.fetch(_q("""
                SELECT id::text as id, source_type as description,
                       source_id as partner, confidence as amount,
                       status, 'evidence_bundle' as source_table
                FROM evidence_bundles
                WHERE tenant_id = %s AND source_id ILIKE %s
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, like, limit)
            results += [_safe(r) for r in rows]
        except Exception as e:
            log.debug("search evidence_bundles: %s", e)

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
# P0-5: New RS.ge / triangle / risk tools
# ─────────────────────────────────────────────────────────────

async def _get_rsge_document_status(params: dict, tenant_id: str) -> dict:
    """Look up a waybill or tax invoice by number. Returns redacted summary only.
    No raw payload, no secret values, no cross-tenant data.
    """
    doc_number = (
        params.get("document_number")
        or params.get("waybill_number")
        or params.get("invoice_number")
        or params.get("query")
        or ""
    ).strip()
    if not doc_number:
        return {"error": "document_number required"}

    like = f"%{doc_number}%"
    found: list[dict] = []

    async with get_conn() as conn:
        try:
            rows = await conn.fetch(_q("""
                SELECT id, waybill_number, waybill_date, seller_name, buyer_name,
                       total_amount, vat_amount, status, version
                FROM waybills
                WHERE tenant_id = %s AND waybill_number ILIKE %s
                ORDER BY id DESC LIMIT 5
            """), tenant_id, like)
            for r in rows:
                d = _safe(r)
                d["source_table"] = "waybill"
                found.append(d)
        except Exception as e:
            log.debug("get_rsge_document_status waybills: %s", e)

        try:
            rows = await conn.fetch(_q("""
                SELECT id, invoice_number, invoice_series, invoice_date,
                       seller_name, buyer_name, total_amount, vat_amount,
                       status, related_waybill_number
                FROM tax_invoices
                WHERE tenant_id = %s AND (invoice_number ILIKE %s OR invoice_series ILIKE %s)
                ORDER BY id DESC LIMIT 5
            """), tenant_id, like, like)
            for r in rows:
                d = _safe(r)
                d["source_table"] = "tax_invoice"
                found.append(d)
        except Exception as e:
            log.debug("get_rsge_document_status tax_invoices: %s", e)

    if not found:
        return {
            "approval_required": False,
            "found": False,
            "message": f"'{doc_number}' ნომრის დოკუმენტი ვერ მოიძებნა",
        }
    return {
        "approval_required": False,
        "found": True,
        "count": len(found),
        "documents": found,
        "summary": f"'{doc_number}' — {len(found)} დოკუმენტი",
    }


async def _get_triangle_match_status(params: dict, tenant_id: str) -> dict:
    """Return 3-way match status for a waybill / invoice combination.
    Shows match_score, mismatch fields, risk level. Read-only.
    """
    query = (
        params.get("query")
        or params.get("waybill_number")
        or params.get("invoice_number")
        or ""
    ).strip()
    limit = int(params.get("limit", 10))

    async with get_conn() as conn:
        try:
            if query:
                rows = await conn.fetch(_q("""
                    SELECT tm.id, tm.match_score, tm.match_status, tm.mismatch_fields,
                           tm.waybill_total, tm.tax_invoice_total, tm.commercial_invoice_total,
                           tm.amount_diff, tm.journal_draft_id, tm.matched_at,
                           w.waybill_number, w.seller_name,
                           ti.invoice_number
                    FROM triangle_matches tm
                    LEFT JOIN waybills w      ON w.id = tm.waybill_id      AND w.tenant_id = %s
                    LEFT JOIN tax_invoices ti ON ti.id = tm.tax_invoice_id AND ti.tenant_id = %s
                    WHERE tm.tenant_id = %s
                      AND (w.waybill_number ILIKE %s OR ti.invoice_number ILIKE %s
                           OR w.seller_name ILIKE %s)
                    ORDER BY tm.id DESC LIMIT %s
                """), tenant_id, tenant_id, tenant_id, f"%{query}%", f"%{query}%",
                    f"%{query}%", limit)
            else:
                rows = await conn.fetch(_q("""
                    SELECT tm.id, tm.match_score, tm.match_status, tm.mismatch_fields,
                           tm.waybill_total, tm.tax_invoice_total, tm.commercial_invoice_total,
                           tm.amount_diff, tm.journal_draft_id, tm.matched_at,
                           w.waybill_number, w.seller_name,
                           ti.invoice_number
                    FROM triangle_matches tm
                    LEFT JOIN waybills w      ON w.id = tm.waybill_id      AND w.tenant_id = %s
                    LEFT JOIN tax_invoices ti ON ti.id = tm.tax_invoice_id AND ti.tenant_id = %s
                    WHERE tm.tenant_id = %s
                    ORDER BY tm.id DESC LIMIT %s
                """), tenant_id, tenant_id, tenant_id, limit)

            matches = []
            for r in rows:
                d = _safe(r)
                mf = d.get("mismatch_fields") or []
                risk = "LOW"
                score = float(d.get("match_score") or 0)
                if d.get("match_status") == "mismatch" or score < 0.5:
                    risk = "HIGH"
                elif score < 0.8 or mf:
                    risk = "MEDIUM"
                d["risk_level"] = risk
                matches.append(d)

        except Exception as e:
            log.debug("get_triangle_match_status: %s", e)
            matches = []

    return {
        "approval_required": False,
        "count": len(matches),
        "matches": matches,
        "summary": f"{len(matches)} triangle match{'es' if len(matches) != 1 else ''}",
    }


async def _get_accounting_risk_summary(params: dict, tenant_id: str) -> dict:
    """Risk summary: missing docs, duplicates, FX missing, period lock, VAT mismatch.
    Read-only. Never exposes secrets.
    """
    from datetime import date as _today_cls
    risks: list[dict] = []

    async with get_conn() as conn:
        # 1. Waybills without a matched tax invoice
        try:
            cnt = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM waybills w
                WHERE w.tenant_id = %s AND w.status = 'imported'
                  AND NOT EXISTS (
                      SELECT 1 FROM tax_invoices ti
                      WHERE ti.tenant_id = w.tenant_id
                        AND ti.related_waybill_id = w.id
                  )
            """), tenant_id)
            if (cnt or 0) > 0:
                risks.append({"type": "WAYBILL_WITHOUT_INVOICE", "count": int(cnt),
                               "severity": "HIGH",
                               "message": f"{cnt} ზედნადები სფ-ის გარეშე"})
        except Exception as e:
            log.debug("risk waybill_without_invoice: %s", e)

        # 2. Triangle mismatches
        try:
            cnt = await conn.fetchval(_q(
                "SELECT COUNT(*) FROM triangle_matches "
                "WHERE tenant_id = %s AND match_status = 'mismatch'"
            ), tenant_id)
            if (cnt or 0) > 0:
                risks.append({"type": "TRIANGLE_MISMATCH", "count": int(cnt),
                               "severity": "HIGH",
                               "message": f"{cnt} დოკუმენტი შეუსაბამობით"})
        except Exception as e:
            log.debug("risk triangle_mismatch: %s", e)

        # 3. FX rate missing
        try:
            fx_cnt = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM currency_rates
                WHERE updated_at >= NOW() - INTERVAL '7 days'
            """))
            if (fx_cnt or 0) == 0:
                risks.append({"type": "FX_RATE_MISSING", "count": 1,
                               "severity": "MEDIUM",
                               "message": "currency_rates ცარიელია — არა-GEL posting დაბლოკილია"})
        except Exception as e:
            log.debug("risk fx_rate: %s", e)

        # 4. Period lock status
        try:
            _now = _today_cls.today()
            lock_row = await conn.fetchrow(_q("""
                SELECT 1 FROM period_locks
                WHERE tenant_id = %s AND period_year = %s
                  AND (period_month = 0 OR period_month = %s)
                  AND unlocked_at IS NULL
                LIMIT 1
            """), tenant_id, _now.year, _now.month)
            if lock_row:
                risks.append({"type": "PERIOD_LOCKED", "count": 1,
                               "severity": "MEDIUM",
                               "message": f"{_now.year}-{_now.month:02d} პერიოდი დახურულია"})
        except Exception as e:
            log.debug("risk period_lock: %s", e)

        # 5. High-amount pending drafts without account codes
        try:
            cnt = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM journal_drafts
                WHERE tenant_id = %s AND status IN ('pending_approval','drafted')
                  AND amount >= 50000
                  AND (debit_account IS NULL OR credit_account IS NULL)
            """), tenant_id)
            if (cnt or 0) > 0:
                risks.append({"type": "HIGH_AMOUNT_MISSING_ACCOUNTS", "count": int(cnt),
                               "severity": "HIGH",
                               "message": f"{cnt} მაღალი თანხის draft Dr/Cr-ის გარეშე"})
        except Exception as e:
            log.debug("risk high_amount_missing_accounts: %s", e)

        # 6. Low-confidence pending drafts
        try:
            cnt = await conn.fetchval(_q("""
                SELECT COUNT(*) FROM journal_drafts
                WHERE tenant_id = %s AND status IN ('pending_approval','drafted')
                  AND (confidence IS NULL OR confidence < 0.75)
            """), tenant_id)
            if (cnt or 0) > 0:
                risks.append({"type": "LOW_CONFIDENCE_DRAFTS", "count": int(cnt),
                               "severity": "LOW",
                               "message": f"{cnt} draft დაბალი confidence-ით (<75%)"})
        except Exception as e:
            log.debug("risk low_confidence: %s", e)

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    risks.sort(key=lambda r: severity_order.get(r.get("severity", "LOW"), 2))

    high_cnt = sum(1 for r in risks if r.get("severity") == "HIGH")
    med_cnt  = sum(1 for r in risks if r.get("severity") == "MEDIUM")

    return {
        "approval_required": False,
        "risk_count": len(risks),
        "high_severity": high_cnt,
        "medium_severity": med_cnt,
        "risks": risks,
        "summary": (
            f"⚠️ {high_cnt} HIGH + {med_cnt} MEDIUM risks"
            if risks else "✅ Risk summary clear"
        ),
    }


# ─────────────────────────────────────────────────────────────
# Bank transactions tools
# ─────────────────────────────────────────────────────────────

async def _get_bank_transactions(params: dict, tenant_id: str) -> dict:
    """Search bank statement transactions.
    params: partner, amount_min, amount_max, date_from, date_to, unreconciled_only, limit
    """
    partner = (params.get("partner") or "").strip()
    amount_min = params.get("amount_min")
    amount_max = params.get("amount_max")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    unreconciled_only = bool(params.get("unreconciled_only", False))
    limit = min(int(params.get("limit") or 50), 100)

    conditions = ["bt.tenant_id = %s"]
    args: list = [tenant_id]

    if partner:
        conditions.append("LOWER(COALESCE(bt.description,'') || ' ' || COALESCE(bt.partner,'')) LIKE %s")
        args.append(f"%{partner.lower()}%")
    if amount_min is not None:
        conditions.append("ABS(bt.amount) >= %s")
        args.append(float(amount_min))
    if amount_max is not None:
        conditions.append("ABS(bt.amount) <= %s")
        args.append(float(amount_max))
    if date_from:
        conditions.append("bt.date >= %s")
        args.append(str(date_from))
    if date_to:
        conditions.append("bt.date <= %s")
        args.append(str(date_to))
    if unreconciled_only:
        conditions.append("""
            NOT EXISTS (
                SELECT 1 FROM bank_reconciliations br
                WHERE br.bank_transaction_id::text = bt.id::text
                  AND br.tenant_id = %s
            )
        """)
        args.append(tenant_id)

    where = " AND ".join(conditions)
    args.append(limit)

    async with get_conn() as conn:
        rows = await conn.fetch(_q(f"""
            SELECT bt.id, bt.date, bt.description, bt.partner,
                   bt.amount, bt.currency, bt.balance, bt.operation_code,
                   br.id IS NOT NULL AS is_reconciled,
                   jd.id AS draft_id, jd.description AS draft_description
            FROM bank_transactions bt
            LEFT JOIN bank_reconciliations br
                ON br.bank_transaction_id::text = bt.id::text
               AND br.tenant_id = %s
            LEFT JOIN journal_drafts jd
                ON jd.bank_txn_id::text = bt.id::text
               AND jd.tenant_id = %s
            WHERE {where}
            ORDER BY bt.date DESC
            LIMIT %s
        """), tenant_id, tenant_id, *args)

    results = []
    for r in rows:
        results.append({
            "id": str(r["id"]),
            "date": str(r["date"]) if r["date"] else None,
            "description": r["description"],
            "partner": r["partner"],
            "amount": float(r["amount"] or 0),
            "currency": r["currency"] or "GEL",
            "balance": float(r["balance"] or 0) if r["balance"] is not None else None,
            "operation_code": r["operation_code"],
            "is_reconciled": bool(r["is_reconciled"]),
            "matched_draft_id": r["draft_id"],
            "matched_draft_description": r["draft_description"],
        })

    unreconciled_count = sum(1 for r in results if not r["is_reconciled"])
    return {
        "count": len(results),
        "unreconciled_in_results": unreconciled_count,
        "transactions": results,
        "filters_applied": {
            "partner": partner or None,
            "amount_min": amount_min,
            "amount_max": amount_max,
            "date_from": date_from,
            "date_to": date_to,
            "unreconciled_only": unreconciled_only,
        },
    }


async def _get_payment_status(params: dict, tenant_id: str) -> dict:
    """Check payment status for a specific invoice or waybill.
    params: invoice_id OR waybill_number OR invoice_number, amount (optional for cross-check)
    """
    invoice_id = params.get("invoice_id")
    invoice_number = (params.get("invoice_number") or "").strip()
    waybill_number = (params.get("waybill_number") or "").strip()
    expected_amount = params.get("amount")

    if not any([invoice_id, invoice_number, waybill_number]):
        return {"error": "invoice_id, invoice_number, ან waybill_number საჭიროა"}

    async with get_conn() as conn:
        # Find the invoice / waybill
        doc = None
        doc_type = None
        doc_amount = None

        if invoice_id or invoice_number:
            cond = "id = %s" if invoice_id else "LOWER(invoice_number) = LOWER(%s)"
            val = invoice_id if invoice_id else invoice_number
            row = await conn.fetchrow(_q(f"""
                SELECT id, invoice_number, partner AS partner_name,
                       total AS total_amount, currency, status, due_date
                FROM invoices WHERE tenant_id = %s AND {cond}
            """), tenant_id, val)
            if row:
                doc = dict(row)
                doc_type = "invoice"
                doc_amount = float(row["total_amount"] or 0)

        if not doc and waybill_number:
            row = await conn.fetchrow(_q("""
                SELECT id, waybill_number, seller_name, buyer_name,
                       total_amount, status, waybill_date
                FROM waybills WHERE tenant_id = %s AND LOWER(waybill_number) = LOWER(%s)
            """), tenant_id, waybill_number)
            if row:
                doc = dict(row)
                doc_type = "waybill"
                doc_amount = float(row["total_amount"] or 0)

        if not doc:
            return {"found": False, "message": "დოკუმენტი ვერ მოიძებნა"}

        # Find matched journal draft
        draft_rows = await conn.fetch(_q("""
            SELECT id, description, amount, status, date, reconciled, bank_txn_id
            FROM journal_drafts
            WHERE tenant_id = %s
              AND (
                LOWER(description) LIKE LOWER(%s)
                OR ABS(COALESCE(amount,0) - %s) < 1.0
              )
            ORDER BY ABS(COALESCE(amount,0) - %s)
            LIMIT 5
        """), tenant_id,
             f"%{(doc.get('invoice_number') or doc.get('waybill_number') or '')}%",
             doc_amount, doc_amount)

        # Find bank transactions that match by amount
        bank_rows = await conn.fetch(_q("""
            SELECT bt.id, bt.date, bt.description, bt.amount, bt.currency,
                   br.id IS NOT NULL AS is_reconciled
            FROM bank_transactions bt
            LEFT JOIN bank_reconciliations br
                ON br.bank_transaction_id::text = bt.id::text AND br.tenant_id = %s
            WHERE bt.tenant_id = %s
              AND ABS(ABS(bt.amount) - %s) < 1.0
            ORDER BY bt.date DESC
            LIMIT 5
        """), tenant_id, tenant_id, doc_amount)

    paid_amount = sum(
        float(r["amount"] or 0) for r in bank_rows if float(r["amount"] or 0) > 0
    )

    if doc_amount and paid_amount >= doc_amount * 0.99:
        payment_status = "გადახდილია"
    elif paid_amount > 0:
        payment_status = "ნაწილობრივ გადახდილია"
    elif paid_amount > doc_amount * 1.01:
        payment_status = "ზედმეტად გადახდილია"
    else:
        payment_status = "გადასარიცხია"

    for k, v in doc.items():
        if hasattr(v, "isoformat"):
            doc[k] = str(v)
        elif hasattr(v, "__float__"):
            try:
                doc[k] = float(v)
            except Exception:
                pass

    return {
        "found": True,
        "document_type": doc_type,
        "document": doc,
        "expected_amount": doc_amount,
        "paid_amount": paid_amount,
        "payment_status": payment_status,
        "matched_bank_transactions": [
            {
                "id": str(r["id"]),
                "date": str(r["date"]) if r["date"] else None,
                "description": r["description"],
                "amount": float(r["amount"] or 0),
                "currency": r["currency"],
                "is_reconciled": bool(r["is_reconciled"]),
            }
            for r in bank_rows
        ],
        "matched_journal_drafts": [
            {
                "id": r["id"],
                "description": r["description"],
                "amount": float(r["amount"] or 0),
                "status": r["status"],
                "date": str(r["date"]) if r["date"] else None,
                "reconciled": bool(r["reconciled"]),
            }
            for r in draft_rows
        ],
    }


# ─────────────────────────────────────────────────────────────
# Sprint 2 — Cross-reference tools
# ─────────────────────────────────────────────────────────────

async def _get_contracts(params: dict, tenant_id: str) -> dict:
    """Search contracts by party name, type, or status.
    params: party_name, contract_type, status, active_only, limit
    """
    party_name = (params.get("party_name") or params.get("partner") or "").strip()
    contract_type = (params.get("contract_type") or "").strip()
    status = (params.get("status") or "").strip()
    active_only = bool(params.get("active_only", False))
    limit = min(int(params.get("limit") or 20), 50)

    conditions = ["c.tenant_id = %s"]
    args: list = [tenant_id]

    if party_name:
        conditions.append("LOWER(COALESCE(c.party_name,'') || ' ' || COALESCE(c.title,'')) LIKE %s")
        args.append(f"%{party_name.lower()}%")
    if contract_type:
        conditions.append("c.contract_type = %s")
        args.append(contract_type)
    if status:
        conditions.append("c.status = %s")
        args.append(status)
    if active_only:
        from datetime import date as _dt
        conditions.append("(c.end_date IS NULL OR c.end_date >= %s)")
        args.append(str(_dt.today()))
        conditions.append("c.status NOT IN ('cancelled','expired','terminated')")

    where = " AND ".join(conditions)
    args.append(limit)

    async with get_conn() as conn:
        rows = await conn.fetch(_q(f"""
            SELECT c.id, c.contract_number, c.title, c.party_name, c.party_tax_id,
                   c.contract_type, c.status, c.value, c.currency,
                   c.start_date, c.end_date, c.payment_terms, c.auto_renew,
                   c.created_at,
                   COUNT(cm.id) FILTER (WHERE cm.status = 'pending' AND cm.due_date < NOW()) AS overdue_milestones
            FROM contracts c
            LEFT JOIN contract_milestones cm
                ON cm.contract_id = c.id AND cm.tenant_id = c.tenant_id
            WHERE {where}
            GROUP BY c.id
            ORDER BY c.created_at DESC
            LIMIT %s
        """), *args)

        total = await conn.fetchval(_q(
            "SELECT COUNT(*) FROM contracts WHERE tenant_id = %s"
        ), tenant_id) or 0

    contracts = [_safe(r) for r in rows]
    overdue_total = sum(int(c.get("overdue_milestones") or 0) for c in contracts)

    return {
        "approval_required": False,
        "count": len(contracts),
        "total_in_db": int(total),
        "overdue_milestones_total": overdue_total,
        "contracts": contracts,
        "summary": (
            f"{len(contracts)} კონტრაქტი"
            + (f", {overdue_total} ვადაგადაცილებული milestone" if overdue_total else "")
        ),
    }


async def _get_payroll_status(params: dict, tenant_id: str) -> dict:
    """Check RS.ge payroll submission status for a period.
    params: period (YYYY-MM, default current month), run_id
    """
    from datetime import date as _dt
    period = (params.get("period") or "").strip()
    if not period:
        today = _dt.today()
        period = f"{today.year}-{today.month:02d}"
    run_id = params.get("run_id")

    async with get_conn() as conn:
        if run_id:
            rows = await conn.fetch(_q("""
                SELECT id, run_id, period, status, submission_ref,
                       submitted_at, resolved_at, notes, created_at, updated_at
                FROM payroll_submissions
                WHERE tenant_id = %s AND run_id = %s
                ORDER BY created_at DESC LIMIT 5
            """), tenant_id, int(run_id))
        else:
            rows = await conn.fetch(_q("""
                SELECT id, run_id, period, status, submission_ref,
                       submitted_at, resolved_at, notes, created_at, updated_at
                FROM payroll_submissions
                WHERE tenant_id = %s AND period = %s
                ORDER BY created_at DESC LIMIT 5
            """), tenant_id, period)

        # Also get last 3 periods for context
        recent = await conn.fetch(_q("""
            SELECT period, status, submission_ref, submitted_at
            FROM payroll_submissions
            WHERE tenant_id = %s
            ORDER BY created_at DESC LIMIT 6
        """), tenant_id)

    submissions = [_safe(r) for r in rows]
    recent_list = [_safe(r) for r in recent]

    if not submissions:
        return {
            "approval_required": False,
            "found": False,
            "period": period,
            "message": f"{period} პერიოდისთვის payroll submission ვერ მოიძებნა",
            "recent_submissions": recent_list,
        }

    latest = submissions[0]
    status = latest.get("status", "unknown")
    status_ge = {
        "draft":     "მომზადებულია",
        "submitted": "გაგზავნილია RS.ge-ზე",
        "accepted":  "მიღებულია RS.ge-ზე",
        "rejected":  "უარყოფილია RS.ge-ზე",
    }.get(status, status)

    return {
        "approval_required": False,
        "found": True,
        "period": period,
        "latest_status": status,
        "status_georgian": status_ge,
        "submission_ref": latest.get("submission_ref"),
        "submitted_at": latest.get("submitted_at"),
        "resolved_at": latest.get("resolved_at"),
        "notes": latest.get("notes"),
        "all_submissions_for_period": submissions,
        "recent_submissions": recent_list,
        "summary": f"{period} payroll: {status_ge}",
    }


async def _get_posting_log(params: dict, tenant_id: str) -> dict:
    """Look up ERP posting history for a journal draft.
    params: draft_id (required), target_system, limit
    """
    draft_id = params.get("draft_id")
    target_system = (params.get("target_system") or "").strip()
    limit = min(int(params.get("limit") or 10), 50)

    if not draft_id:
        return {"error": "draft_id required"}

    conditions = ["pl.tenant_id = %s", "pl.draft_id = %s"]
    args: list = [tenant_id, int(draft_id)]

    if target_system:
        conditions.append("pl.target_system = %s")
        args.append(target_system)

    where = " AND ".join(conditions)
    args.append(limit)

    async with get_conn() as conn:
        rows = await conn.fetch(_q(f"""
            SELECT pl.id, pl.draft_id, pl.target_system, pl.status,
                   pl.error_message, pl.mode, pl.actor, pl.connector,
                   pl.created_at,
                   jd.description AS draft_description,
                   jd.amount AS draft_amount,
                   jd.status AS draft_status
            FROM posting_logs pl
            LEFT JOIN journal_drafts jd
                ON jd.id = pl.draft_id AND jd.tenant_id = pl.tenant_id
            WHERE {where}
            ORDER BY pl.id DESC
            LIMIT %s
        """), *args)

    logs = []
    for r in rows:
        d = _safe(r)
        status = d.get("status", "")
        d["status_georgian"] = {
            "success":  "წარმატებულია",
            "failed":   "წარუმატებელია",
            "pending":  "მუშავდება",
            "dry_run":  "ტესტ-რეჟიმი",
            "skipped":  "გამოტოვებულია",
        }.get(status, status)
        logs.append(d)

    last_success = next((l for l in logs if l.get("status") == "success"), None)
    last_fail = next((l for l in logs if l.get("status") == "failed"), None)

    return {
        "approval_required": False,
        "draft_id": draft_id,
        "count": len(logs),
        "last_success": last_success,
        "last_failure": last_fail,
        "logs": logs,
        "summary": (
            f"draft #{draft_id}: {len(logs)} posting ჩანაწერი"
            + (f" — ბოლო: {logs[0].get('status_georgian','')}" if logs else " — ისტორია ცარიელია")
        ),
    }


async def _get_monthly_close_status(params: dict, tenant_id: str) -> dict:
    """Run the monthly close checklist for a period.
    params: month (YYYY-MM, default current month)
    """
    from datetime import date as _dt
    month = (params.get("month") or params.get("period") or "").strip()
    if not month:
        today = _dt.today()
        month = f"{today.year}-{today.month:02d}"

    try:
        from app.api.services.monthly_close_service import run_checklist
        checklist = await run_checklist(tenant_id, month)
    except Exception as e:
        log.warning("monthly_close checklist failed: %s", e)
        return {"error": str(e), "month": month}

    ok_count = sum(1 for c in checklist if c.get("status") == "ok")
    failed = [c for c in checklist if c.get("status") == "failed"]
    warnings = [c for c in checklist if c.get("status") == "warning"]

    overall = (
        "დახურვა შესაძლებელია" if not failed else
        "დახურვა შეუძლებელია" if len(failed) >= 2 else
        "პრობლემები გამოვლინდა"
    )

    return {
        "approval_required": False,
        "month": month,
        "overall_status": overall,
        "ok_count": ok_count,
        "failed_count": len(failed),
        "warning_count": len(warnings),
        "checklist": checklist,
        "failed_items": [c["name"] for c in failed],
        "warning_items": [c["name"] for c in warnings],
        "summary": (
            f"{month}: {overall} — "
            f"{ok_count}/{len(checklist)} checklist item OK"
            + (f", {len(failed)} წარუმატებელი" if failed else "")
            + (f", {len(warnings)} გაფრთხილება" if warnings else "")
        ),
    }


# ─────────────────────────────────────────────────────────────
# Sprint 3A — RS.ge document list tool
# ─────────────────────────────────────────────────────────────

async def _get_rsge_documents(params: dict, tenant_id: str) -> dict:
    """List RS.ge-imported waybills and tax invoices.
    params: doc_type ('waybill'|'tax_invoice'|'both'), seller_inn, buyer_inn, status, limit
    """
    doc_type = (params.get("doc_type") or "both").strip().lower()
    seller_inn = (params.get("seller_inn") or "").strip()
    buyer_inn = (params.get("buyer_inn") or "").strip()
    status = (params.get("status") or "").strip()
    limit = min(int(params.get("limit") or 20), 50)

    waybills: list[dict] = []
    tax_invoices_: list[dict] = []

    async with get_conn() as conn:
        if doc_type in ("waybill", "both"):
            wb_conds = ["w.tenant_id = %s", "w.source = 'rsge_import'"]
            wb_args: list = [tenant_id]
            if seller_inn:
                wb_conds.append("w.seller_inn = %s"); wb_args.append(seller_inn)
            if buyer_inn:
                wb_conds.append("w.buyer_inn = %s"); wb_args.append(buyer_inn)
            if status:
                wb_conds.append("w.status = %s"); wb_args.append(status)
            wb_args.append(limit)
            try:
                rows = await conn.fetch(_q(f"""
                    SELECT w.id, w.waybill_number, w.waybill_date,
                           w.seller_inn, w.seller_name, w.buyer_inn, w.buyer_name,
                           w.total_amount, w.vat_amount, w.status, w.created_at,
                           tm.match_status, tm.match_score
                    FROM waybills w
                    LEFT JOIN triangle_matches tm ON tm.waybill_id=w.id AND tm.tenant_id=w.tenant_id
                    WHERE {' AND '.join(wb_conds)}
                    ORDER BY w.created_at DESC LIMIT %s
                """), *wb_args)
                waybills = [_safe(r) for r in rows]
            except Exception as e:
                log.debug("get_rsge_documents waybills: %s", e)

        if doc_type in ("tax_invoice", "both"):
            ti_conds = ["ti.tenant_id = %s", "ti.source = 'rsge_import'"]
            ti_args: list = [tenant_id]
            if seller_inn:
                ti_conds.append("ti.seller_inn = %s"); ti_args.append(seller_inn)
            if buyer_inn:
                ti_conds.append("ti.buyer_inn = %s"); ti_args.append(buyer_inn)
            if status:
                ti_conds.append("ti.status = %s"); ti_args.append(status)
            ti_args.append(limit)
            try:
                rows = await conn.fetch(_q(f"""
                    SELECT ti.id, ti.invoice_number, ti.invoice_series, ti.invoice_date,
                           ti.seller_inn, ti.seller_name, ti.buyer_inn, ti.buyer_name,
                           ti.total_amount, ti.vat_amount, ti.status,
                           ti.related_waybill_number, ti.created_at,
                           tm.match_status, tm.match_score
                    FROM tax_invoices ti
                    LEFT JOIN triangle_matches tm ON tm.tax_invoice_id=ti.id AND tm.tenant_id=ti.tenant_id
                    WHERE {' AND '.join(ti_conds)}
                    ORDER BY ti.created_at DESC LIMIT %s
                """), *ti_args)
                tax_invoices_ = [_safe(r) for r in rows]
            except Exception as e:
                log.debug("get_rsge_documents tax_invoices: %s", e)

    total = len(waybills) + len(tax_invoices_)
    matched = sum(
        1 for d in (waybills + tax_invoices_)
        if d.get("match_status") in ("full_match", "partial_match")
    )

    return {
        "approval_required": False,
        "total": total,
        "waybills": waybills,
        "tax_invoices": tax_invoices_,
        "matched_count": matched,
        "summary": (
            f"RS.ge: {len(waybills)} ზედნადები, {len(tax_invoices_)} ფაქტურა"
            + (f" ({matched} matched)" if matched else "")
        ),
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
    "explain_draft":              _explain_draft,
    "show_risks":                 _show_risks,
    "show_pending_tasks":         _show_pending_tasks,
    "financial_summary":          _financial_summary,
    "tax_summary":                _tax_summary,
    "search_documents":           _search_documents,
    "prepare_approval_preview":   _prepare_approval_preview,
    "prepare_posting_preview":    _prepare_posting_preview,
    "get_rsge_document_status":   _get_rsge_document_status,
    "get_triangle_match_status":  _get_triangle_match_status,
    "get_accounting_risk_summary": _get_accounting_risk_summary,
    "get_bank_transactions":        _get_bank_transactions,
    "get_payment_status":           _get_payment_status,
    # Sprint 2
    "get_contracts":                _get_contracts,
    "get_payroll_status":           _get_payroll_status,
    "get_posting_log":              _get_posting_log,
    "get_monthly_close_status":     _get_monthly_close_status,
    # Sprint 3A
    "get_rsge_documents":           _get_rsge_documents,
}
