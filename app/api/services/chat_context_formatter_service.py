"""
app/api/services/chat_context_formatter_service.py

Renders the context dict produced by chat_context_service.build_chat_context()
into the REAL SYSTEM CONTEXT block that Claude receives as a prompt prefix.
"""
from __future__ import annotations


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

    # Queue (priority-ordered pending drafts)
    if ctx.get("queue"):
        has_data = True
        lines.append("\n[Queue — Priority Order (lowest confidence first)]")
        for d in ctx["queue"]:
            lines.append(
                f"  #{d.get('id')} | {d.get('description')} | "
                f"{_fmt_amount(d.get('amount'))} GEL | {d.get('status')} | "
                f"conf:{_fmt_pct(d.get('confidence'))} | partner:{d.get('partner') or 'N/A'}"
            )

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

    # Bank summary
    if ctx.get("bank_summary"):
        bs = ctx["bank_summary"]
        has_data = True
        totals_str = " | ".join(f"{cur}:{_fmt_amount(amt)}" for cur, amt in bs.get("totals", {}).items())
        lines.append(f"\n[Bank Summary] {bs.get('accounts_count')} accounts | {totals_str}")

    # Bank accounts detail
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

    # Waybills
    if ctx.get("waybills"):
        has_data = True
        lines.append("\n[Waybills]")
        for w in ctx["waybills"]:
            lines.append(
                f"  #{w.get('waybill_number')} | {w.get('seller_name')} → {w.get('buyer_name')} | "
                f"{_fmt_amount(w.get('total_amount'))} GEL | {w.get('status')}"
            )

    # Tax invoices
    if ctx.get("tax_invoices"):
        has_data = True
        lines.append("\n[Tax Invoices (ელ-ფაქტურა)]")
        for ti in ctx["tax_invoices"]:
            lines.append(
                f"  #{ti.get('invoice_number')} | {ti.get('seller_name')} → {ti.get('buyer_name')} | "
                f"total:{_fmt_amount(ti.get('total_amount'))} VAT:{_fmt_amount(ti.get('vat_amount'))} GEL | {ti.get('status')}"
            )

    # Notifications
    if ctx.get("notifications"):
        unread = [n for n in ctx["notifications"] if not n.get("is_read")]
        has_data = True
        lines.append(f"\n[Notifications] {len(ctx['notifications'])} total, {len(unread)} unread")
        for n in ctx["notifications"][:5]:
            read_mark = "" if n.get("is_read") else "🔴 "
            lines.append(f"  {read_mark}{n.get('type')} | {n.get('title')} | {n.get('message', '')[:80]}")

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

    if not has_data:
        return (
            "REAL SYSTEM CONTEXT:\n"
            "[სისტემაში ამ მომენტისთვის მონაცემები ვერ ჩაიტვირთა ან შეკითხვა "
            "არ ეხება კონკრეტულ ჩანაწერს. "
            "ნებისმიერი თანხა, სახელი ან სტატუსი, რომელიც ზემოთ არ ჩანს, "
            "გამოიგონო ნუ — თქვი: 'ამ ინფორმაციას სისტემაში ვერ ვპოულობ.']"
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────
# Formatting helpers
# ─────────────────────────────────────────────────────────────

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
