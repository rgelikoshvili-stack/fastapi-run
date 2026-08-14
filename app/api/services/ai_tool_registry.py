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
}
