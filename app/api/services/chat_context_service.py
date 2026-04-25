"""
app/api/services/chat_context_service.py
Bridge Hub — AI Chat Orchestrator Context Builder

Fetches real DB data from ALL Bridge Hub modules for Claude.
Intent detection picks which modules to load — no over-fetching.
All queries are tenant-scoped (WHERE tenant_id = %s).

Modules covered:
  Approval, Documents, Decision Engine, Bank,
  Payroll, Tax, Reports, Learning, Audit, Outgoing Invoices
"""
from __future__ import annotations

import logging
from typing import Optional

import psycopg2.extras

from app.api.db import get_db

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Intent detection — which modules to load
# ─────────────────────────────────────────────────────────────

_INTENT_MAP = {
    "approval":  ["approve", "approval", "დამტკიც", "draft", "დრაფტ", "pending", "queue", "reject", "უარყოფ"],
    "bank":      ["bank", "ბანკ", "transaction", "ტრანზაქცი", "balance", "ბალანს", "tbc", "bog", "cash", "ნაშთ"],
    "invoices":  ["invoice", "ინვოის", "outgoing", "გამავალ", "receivable", "მისაღებ", "customer", "კლიენტ"],
    "documents": ["document", "დოკუმენტ", "waybill", "სასაქონლო", "tax invoice", "ატვირთ", "upload", "ocr"],
    "payroll":   ["payroll", "ხელფას", "salary", "employee", "თანამშრომ", "pit", "payg", "gross", "net"],
    "tax":       ["vat", "დღგ", "cit", "მოგება", "withholding", "rs.ge", "revenue service", "tax", "გადასახად"],
    "reports":   ["report", "ანგარიშ", "p&l", "profit", "loss", "trial balance", "cash flow", "statement"],
    "audit":     ["audit", "history", "ისტორი", "log", "ლოგ", "who", "ვინ", "when", "როდის", "changed", "შეცვლა"],
    "learning":  ["pattern", "ნიმუშ", "learn", "სწავლ", "rule", "წეს", "confidence", "accuracy"],
    "decisions": ["decision", "გადაწყვეტილ", "recommend", "რეკომენდ", "suggest", "engine", "autopilot"],
}


def _detect_intents(message: str) -> set[str]:
    msg = message.lower()
    found = set()
    for module, keywords in _INTENT_MAP.items():
        if any(kw in msg for kw in keywords):
            found.add(module)
    # Always load approval as baseline
    found.add("approval")
    return found


# ─────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────

def build_chat_context(
    tenant_id: str,
    message: str,
    draft_id: Optional[int] = None,
) -> dict:
    """
    Build full orchestrator context dict for Claude.

    Returns:
        {
          "draft": dict | None,
          "not_found": bool,
          "pending_count": int,
          "recent_drafts": [...],
          "bank_accounts": [...],
          "bank_transactions": [...],
          "invoices": [...],
          "outgoing_invoices": [...],
          "documents": [...],
          "payroll_drafts": [...],
          "tax_summary": dict | None,
          "reports_summary": dict | None,
          "audit_recent": [...],
          "learning_stats": dict | None,
          "decisions_pending": [...],
          "kpi": dict | None,
          "intents": [str],
        }
    """
    ctx: dict = {
        "draft": None,
        "not_found": False,
        "pending_count": 0,
        "recent_drafts": [],
        "bank_accounts": [],
        "bank_transactions": [],
        "invoices": [],
        "outgoing_invoices": [],
        "documents": [],
        "payroll_drafts": [],
        "tax_summary": None,
        "reports_summary": None,
        "audit_recent": [],
        "learning_stats": None,
        "decisions_pending": [],
        "kpi": None,
        "intents": [],
    }

    intents = _detect_intents(message)
    if draft_id is not None:
        intents.add("approval")
    ctx["intents"] = sorted(intents)

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # ── Specific draft by ID ────────────────────────────
        if draft_id is not None:
            try:
                cur.execute(
                    """
                    SELECT id, description, amount, partner, account_code,
                           debit_account, credit_account, status, confidence,
                           source_type, created_at, date
                    FROM journal_drafts
                    WHERE id = %s AND tenant_id = %s
                    """,
                    (draft_id, tenant_id),
                )
                row = cur.fetchone()
                if row:
                    ctx["draft"] = _safe_dict(row)
                else:
                    ctx["not_found"] = True
            except Exception as e:
                log.warning("draft fetch: %s", e)

        # ── Approval module ─────────────────────────────────
        if "approval" in intents:
            try:
                cur.execute(
                    "SELECT COUNT(*) as cnt FROM journal_drafts "
                    "WHERE status IN ('pending_approval','drafted') AND tenant_id = %s",
                    (tenant_id,),
                )
                row = cur.fetchone()
                ctx["pending_count"] = int(row["cnt"]) if row else 0
            except Exception as e:
                log.warning("pending count: %s", e)

            try:
                exclude = draft_id or -1
                cur.execute(
                    """
                    SELECT id, description, amount, partner, status,
                           account_code, confidence, created_at
                    FROM journal_drafts
                    WHERE tenant_id = %s AND id != %s
                    ORDER BY created_at DESC LIMIT 7
                    """,
                    (tenant_id, exclude),
                )
                ctx["recent_drafts"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("recent_drafts: %s", e)

            try:
                cur.execute(
                    """
                    SELECT COUNT(*) as total,
                           COUNT(CASE WHEN status='pending_approval' THEN 1 END) as pending,
                           COUNT(CASE WHEN status IN ('approved','auto_approved') THEN 1 END) as approved,
                           COUNT(CASE WHEN status='rejected' THEN 1 END) as rejected,
                           COALESCE(AVG(confidence), 0) as avg_confidence
                    FROM journal_drafts WHERE tenant_id = %s
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()
                if row:
                    ctx["kpi"] = {
                        "total_drafts": int(row["total"]),
                        "pending": int(row["pending"]),
                        "approved": int(row["approved"]),
                        "rejected": int(row["rejected"]),
                        "avg_confidence": round(float(row["avg_confidence"]), 3),
                    }
            except Exception as e:
                log.warning("kpi: %s", e)

        # ── Bank module ─────────────────────────────────────
        if "bank" in intents:
            try:
                cur.execute(
                    "SELECT name, balance, currency, account_type, is_primary "
                    "FROM bank_accounts WHERE tenant_id = %s ORDER BY balance DESC LIMIT 5",
                    (tenant_id,),
                )
                ctx["bank_accounts"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("bank_accounts: %s", e)

            try:
                cur.execute(
                    """
                    SELECT id, date, description, amount, bank, balance
                    FROM bank_transactions
                    WHERE tenant_id = %s
                    ORDER BY date DESC, id DESC LIMIT 10
                    """,
                    (tenant_id,),
                )
                ctx["bank_transactions"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("bank_transactions: %s", e)

        # ── Invoices / Outgoing ─────────────────────────────
        if "invoices" in intents:
            try:
                cur.execute(
                    """
                    SELECT id, number, partner, total, status, due_date, created_at
                    FROM invoices
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC LIMIT 5
                    """,
                    (tenant_id,),
                )
                ctx["invoices"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("invoices: %s", e)

            try:
                cur.execute(
                    """
                    SELECT id, invoice_number, partner_name, total_amount,
                           status, issue_date, due_date
                    FROM outgoing_invoices
                    WHERE tenant_id = %s
                    ORDER BY issue_date DESC LIMIT 5
                    """,
                    (tenant_id,),
                )
                ctx["outgoing_invoices"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("outgoing_invoices: %s", e)

        # ── Documents ───────────────────────────────────────
        if "documents" in intents:
            try:
                cur.execute(
                    """
                    SELECT id, original_filename, document_type, status,
                           amount, partner_name, created_at
                    FROM processed_documents
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC LIMIT 5
                    """,
                    (tenant_id,),
                )
                ctx["documents"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("documents: %s", e)

        # ── Payroll ─────────────────────────────────────────
        if "payroll" in intents:
            try:
                cur.execute(
                    """
                    SELECT id, description, amount, status, created_at
                    FROM journal_drafts
                    WHERE tenant_id = %s
                      AND (source_type = 'payroll' OR description ILIKE '%payroll%'
                           OR description ILIKE '%ხელფას%')
                    ORDER BY created_at DESC LIMIT 5
                    """,
                    (tenant_id,),
                )
                ctx["payroll_drafts"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("payroll_drafts: %s", e)

        # ── Tax summary ─────────────────────────────────────
        if "tax" in intents:
            try:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN credit_account = '3310' THEN amount ELSE 0 END), 0) as vat_payable,
                        COALESCE(SUM(CASE WHEN credit_account = '3320' THEN amount ELSE 0 END), 0) as pit_payable,
                        COALESCE(SUM(CASE WHEN credit_account = '3340' THEN amount ELSE 0 END), 0) as cit_payable
                    FROM journal_drafts
                    WHERE tenant_id = %s AND status IN ('approved','auto_approved')
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()
                if row:
                    ctx["tax_summary"] = {
                        "vat_payable": float(row["vat_payable"]),
                        "pit_payable": float(row["pit_payable"]),
                        "cit_payable": float(row["cit_payable"]),
                    }
            except Exception as e:
                log.warning("tax_summary: %s", e)

        # ── Reports summary ─────────────────────────────────
        if "reports" in intents:
            try:
                cur.execute(
                    """
                    SELECT
                        COALESCE(SUM(CASE WHEN credit_account LIKE '6%%' THEN amount ELSE 0 END), 0) as revenue,
                        COALESCE(SUM(CASE WHEN debit_account  LIKE '7%%' THEN amount ELSE 0 END), 0) as expenses
                    FROM journal_drafts
                    WHERE tenant_id = %s AND status IN ('approved','auto_approved')
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()
                if row:
                    rev = float(row["revenue"])
                    exp = float(row["expenses"])
                    ctx["reports_summary"] = {
                        "revenue": rev,
                        "expenses": exp,
                        "profit": round(rev - exp, 2),
                        "margin_pct": round((rev - exp) / rev * 100, 1) if rev > 0 else 0,
                    }
            except Exception as e:
                log.warning("reports_summary: %s", e)

        # ── Audit log ───────────────────────────────────────
        if "audit" in intents:
            try:
                cur.execute(
                    """
                    SELECT event_type, actor, description, created_at
                    FROM audit_log
                    WHERE (tenant_id IS NULL OR tenant_id::text = %s)
                    ORDER BY created_at DESC LIMIT 10
                    """,
                    (tenant_id,),
                )
                ctx["audit_recent"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("audit_recent: %s", e)

        # ── Learning stats ──────────────────────────────────
        if "learning" in intents:
            try:
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(CASE WHEN status='active' THEN 1 END) as active,
                        COALESCE(AVG(confidence_score), 0) as avg_conf,
                        COUNT(CASE WHEN source='human' THEN 1 END) as human_rules
                    FROM learning_patterns
                    WHERE tenant_id = %s
                    """,
                    (tenant_id,),
                )
                row = cur.fetchone()
                if row:
                    ctx["learning_stats"] = {
                        "total_patterns": int(row["total"]),
                        "active_patterns": int(row["active"]),
                        "avg_confidence": round(float(row["avg_conf"]), 3),
                        "human_rules": int(row["human_rules"]),
                    }
            except Exception as e:
                log.warning("learning_stats: %s", e)

        # ── Decision Engine ─────────────────────────────────
        if "decisions" in intents:
            try:
                cur.execute(
                    """
                    SELECT id, description, amount, confidence, status, created_at
                    FROM journal_drafts
                    WHERE tenant_id = %s AND status = 'pending_approval'
                    ORDER BY confidence ASC LIMIT 5
                    """,
                    (tenant_id,),
                )
                ctx["decisions_pending"] = [_safe_dict(r) for r in cur.fetchall()]
            except Exception as e:
                log.warning("decisions_pending: %s", e)

        cur.close()
        conn.close()

    except Exception as e:
        log.error("build_chat_context failed: %s", e)

    return ctx


def format_context_for_prompt(ctx: dict) -> str:
    """Render context dict → REAL SYSTEM CONTEXT block for Claude."""
    if ctx.get("not_found"):
        return "REAL SYSTEM CONTEXT:\nდრაფტი სისტემაში ვერ მოიძებნა."

    lines = ["REAL SYSTEM CONTEXT:"]
    has_data = False

    def _add(section: str, items):
        nonlocal has_data
        if not items:
            return
        has_data = True
        lines.append(f"\n[{section}]")
        if isinstance(items, list):
            for it in items:
                lines.append("  " + _fmt(it))
        elif isinstance(items, dict):
            for k, v in items.items():
                lines.append(f"  {k}: {v}")

    # Specific draft
    if ctx.get("draft"):
        d = ctx["draft"]
        has_data = True
        lines.append(f"\n[Current Draft #{d.get('id')}]")
        lines.append(f"  Description : {d.get('description')}")
        lines.append(f"  Amount      : {_fmt_amount(d.get('amount'))} GEL")
        lines.append(f"  Partner     : {d.get('partner') or 'N/A'}")
        lines.append(f"  Account     : {d.get('account_code') or 'N/A'}")
        lines.append(f"  Dr/Cr       : {d.get('debit_account')} / {d.get('credit_account')}")
        lines.append(f"  Status      : {d.get('status')}")
        lines.append(f"  Confidence  : {_fmt_pct(d.get('confidence'))}")
        lines.append(f"  Date        : {d.get('date') or d.get('created_at', 'N/A')}")

    # KPI
    if ctx.get("kpi"):
        k = ctx["kpi"]
        has_data = True
        lines.append(
            f"\n[KPI] total={k['total_drafts']} | pending={k['pending']} | "
            f"approved={k['approved']} | rejected={k['rejected']} | "
            f"avg_conf={_fmt_pct(k['avg_confidence'])}"
        )

    if ctx.get("pending_count"):
        has_data = True
        lines.append(f"\n[Approval Queue] {ctx['pending_count']} drafts waiting")

    # Recent drafts
    if ctx.get("recent_drafts"):
        has_data = True
        lines.append("\n[Recent Drafts]")
        for d in ctx["recent_drafts"]:
            lines.append(
                f"  #{d.get('id')} | {d.get('description')} | "
                f"{_fmt_amount(d.get('amount'))} GEL | {d.get('status')} | "
                f"conf:{_fmt_pct(d.get('confidence'))}"
            )

    # Bank
    if ctx.get("bank_accounts"):
        has_data = True
        lines.append("\n[Bank Accounts]")
        for b in ctx["bank_accounts"]:
            primary = " ★" if b.get("is_primary") else ""
            lines.append(f"  {b.get('name')}{primary}: {_fmt_amount(b.get('balance'))} {b.get('currency')}")

    if ctx.get("bank_transactions"):
        has_data = True
        lines.append("\n[Recent Bank Transactions]")
        for t in ctx["bank_transactions"][:5]:
            lines.append(
                f"  {t.get('date')} | {t.get('description')} | "
                f"{_fmt_amount(t.get('amount'))} GEL | bal:{_fmt_amount(t.get('balance'))}"
            )

    # Invoices
    if ctx.get("invoices"):
        _add("Invoices", ctx["invoices"])

    if ctx.get("outgoing_invoices"):
        has_data = True
        lines.append("\n[Outgoing Invoices]")
        for inv in ctx["outgoing_invoices"]:
            lines.append(
                f"  #{inv.get('invoice_number')} | {inv.get('partner_name')} | "
                f"{_fmt_amount(inv.get('total_amount'))} GEL | {inv.get('status')}"
            )

    # Documents
    if ctx.get("documents"):
        has_data = True
        lines.append("\n[Processed Documents]")
        for doc in ctx["documents"]:
            lines.append(
                f"  {doc.get('original_filename')} | {doc.get('document_type')} | "
                f"{doc.get('status')} | {_fmt_amount(doc.get('amount'))} GEL"
            )

    # Payroll
    if ctx.get("payroll_drafts"):
        has_data = True
        lines.append("\n[Payroll Drafts]")
        for p in ctx["payroll_drafts"]:
            lines.append(f"  #{p.get('id')} | {p.get('description')} | {_fmt_amount(p.get('amount'))} GEL | {p.get('status')}")

    # Tax
    if ctx.get("tax_summary"):
        t = ctx["tax_summary"]
        has_data = True
        lines.append(
            f"\n[Tax Payable] VAT:{_fmt_amount(t['vat_payable'])} | "
            f"PIT:{_fmt_amount(t['pit_payable'])} | CIT:{_fmt_amount(t['cit_payable'])} GEL"
        )

    # Reports
    if ctx.get("reports_summary"):
        r = ctx["reports_summary"]
        has_data = True
        lines.append(
            f"\n[P&L Summary] Revenue:{_fmt_amount(r['revenue'])} | "
            f"Expenses:{_fmt_amount(r['expenses'])} | "
            f"Profit:{_fmt_amount(r['profit'])} | Margin:{r['margin_pct']}%"
        )

    # Audit
    if ctx.get("audit_recent"):
        has_data = True
        lines.append("\n[Recent Audit Events]")
        for a in ctx["audit_recent"][:5]:
            lines.append(f"  {a.get('created_at')} | {a.get('event_type')} | {a.get('actor')} | {a.get('description')}")

    # Learning
    if ctx.get("learning_stats"):
        s = ctx["learning_stats"]
        has_data = True
        lines.append(
            f"\n[Learning Patterns] total={s['total_patterns']} active={s['active_patterns']} "
            f"avg_conf={_fmt_pct(s['avg_confidence'])} human_rules={s['human_rules']}"
        )

    # Decision Engine
    if ctx.get("decisions_pending"):
        has_data = True
        lines.append("\n[Low-Confidence Drafts (need review)]")
        for d in ctx["decisions_pending"]:
            lines.append(f"  #{d.get('id')} | {d.get('description')} | conf:{_fmt_pct(d.get('confidence'))}")

    return "\n".join(lines) if has_data else ""


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _safe_dict(row) -> dict:
    """Convert RealDictRow to plain dict with serializable values."""
    d = dict(row)
    for k, v in d.items():
        try:
            import decimal
            if isinstance(v, decimal.Decimal):
                d[k] = float(v)
            elif hasattr(v, "isoformat"):
                d[k] = str(v)
        except Exception:
            pass
    return d


def _fmt_amount(v) -> str:
    try:
        return f"{float(v):,.2f}"
    except Exception:
        return str(v or "N/A")


def _fmt_pct(v) -> str:
    try:
        f = float(v)
        return f"{f:.0%}" if f <= 1.0 else f"{f:.1f}%"
    except Exception:
        return str(v or "N/A")


def _fmt(item) -> str:
    if isinstance(item, dict):
        parts = []
        for k in ["id", "description", "amount", "status", "partner", "date", "created_at"]:
            if k in item and item[k] is not None:
                v = item[k]
                if k == "amount":
                    v = f"{_fmt_amount(v)} GEL"
                parts.append(str(v))
        return " | ".join(parts) if parts else str(item)
    return str(item)
