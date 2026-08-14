"""
Bridge Hub — Claude Chat with Tool Use (MCP-style)
/api/claude/chat  →  Claude can read AND write Bridge Hub data
"""
import os
import io
import json
import logging
from datetime import date
from fastapi import APIRouter, UploadFile, File, Form, Request
from app.api.authz import require_permission
from app.api.response_utils import http_error

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/claude", tags=["Claude Chat"])

# ── Knowledge keyword maps ────────────────────────────────────────────────────
_TAX_KEYWORDS = {
    "vat":          ["დღგ", "vat", "დღგ-ს", "დღგ-ის"],
    "pit":          ["საშემოსავლო", "pit", "income tax", "personal"],
    "cit":          ["მოგების", "cit", "profit tax", "corporate"],
    "withholding":  ["წყაროსთან", "withholding", "retention"],
    "property":     ["ქონება", "property tax"],
    "penalty":      ["სანქცი", "penalty", "fine", "ჯარიმ"],
    "non_resident": ["არარეზიდენტ", "non-resident", "foreign"],
    "micro":        ["მცირე ბიზნეს", "micro", "small business"],
}
_ACC_KEYWORDS = {
    "salary":       ["ხელფას", "salary", "payroll", "payg", "შრომ"],
    "dividends":    ["დივიდენდ", "dividend"],
    "depreciation": ["ამორტიზაც", "depreciation"],
    "fixed_assets": ["ძირითადი საშუალებ", "fixed asset"],
    "inventory":    ["მარაგ", "inventory", "stock"],
    "receivables":  ["მოთხოვნ", "receivable", "debtor"],
    "payables":     ["ვალდებულ", "payable", "creditor"],
    "loan":         ["სესხ", "loan", "credit"],
    "capital":      ["კაპიტალ", "capital", "equity"],
    "principles":   ["პრინციპ", "principle", "standard", "ifrs", "gaap"],
}

SYSTEM_PROMPT = """\
შენ ხარ Bridge Hub AI — ქართული ფინანსური OS-ის AI ბუღალტერი.
შენ შეგიძლია:
• ბუღალტრული გატარებების შექმნა (create_journal_draft) — draft იქმნება PENDING სტატუსით
• გატარებების ძებნა და ნახვა (search_transactions, list_pending_drafts)
• ანგარიშების ნაშთის გამოთვლა (get_account_balance)
• ტრანზაქციის კლასიფიკაცია (classify_transaction)
• დამტკიცების რეკომენდაცია (approve_draft) — AI ვერ ასრულებს თვითონ, ადამიანი ამტკიცებს

ᲛᲜᲘᲨᲕᲜᲔᲚᲝᲕᲐᲜᲘ უსაფრთხოების წესი:
AI ვერ ასრულებს გატარების პირდაპირ დამტკიცებას. approve_draft tool-ი
აბრუნებს დამტკიცების მოთხოვნას ადამიანისთვის. ბუღალტერი ან CFO
ადასტურებს /api/approval/approve/{id} endpoint-ის მეშვეობით.
ეს უზრუნველყოფს: period lock check, CFO gate (≥₾10,000), audit log.

შენი ექსპერტიზა:
• ქართული საგადასახადო კოდექსი — დღგ 18%, საშემოსავლო 20%, მოგების 15%, სოციალური 2%
• IFRS/GAAP ბუღალტრული სტანდარტები
• Bridge Hub COA — 1xxx:აქტივი, 2xxx:გრძვადიდი ვალდ., 3xxx:მოკლევ. ვალდ., 4xxx:კაპიტალი, 5xxx:შემოსავალი, 6xxx:წარმოება, 7xxx:ხარჯი
• ხელფასი (Dr7110/Cr3310), VAT (Dr1430/Cr3350), ფაქტურა (Dr1410/Cr6110)

მოქმედების პრინციპი:
1. თუ მომხმარებელი ითხოვს გატარებას → create_journal_draft-ს გამოიყენე
2. თუ ანგარიშები გაუგია → classify_transaction-ს გამოიყენე პირველ
3. დამტკიცებამდე დაასახელე რა გააკეთე (Dr/Cr) და შეახსენე რომ ადამიანი ამტკიცებს
4. ქართულად ილაპარაკე, სრულად და გარჩეულად
"""

# ── Tool definitions ──────────────────────────────────────────────────────────
TOOLS = [
    {
        "name": "create_journal_draft",
        "description": "ბუღალტრული გატარების შექმნა Bridge Hub-ში. გამოიყენე როდესაც მომხმარებელი ითხოვს ახალი ჩანაწერის, ფაქტურის ან ტრანზაქციის გატარებას.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "ტრანზაქციის სრული აღწერა"},
                "amount":      {"type": "number", "description": "თანხა ლარში (დადებითი)"},
                "debit_account": {"type": "string", "description": "სადებეტო ანგარიშის კოდი (მაგ: 7510)"},
                "credit_account": {"type": "string", "description": "საკრედიტო ანგარიშის კოდი (მაგ: 3350)"},
                "date":        {"type": "string", "description": "თარიღი YYYY-MM-DD (სურვილისამებრ, default: დღეს)"},
                "vendor":      {"type": "string", "description": "მომწოდებელი/კონტრაჰენტი (სურვილისამებრ)"},
            },
            "required": ["description", "amount", "debit_account", "credit_account"],
        },
    },
    {
        "name": "approve_draft",
        "description": (
            "გატარების დამტკიცების მოთხოვნის მომზადება. "
            "AI ვერ ასრულებს პირდაპირ დამტკიცებას — tool-ი აბრუნებს approval_required=true "
            "და ბმულს ბუღალტრისთვის. ადამიანი ადასტურებს /api/approval/approve/{draft_id}."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "integer", "description": "გატარების ID (create_journal_draft-ის შემდეგ ცნობილი)"},
                "comment":  {"type": "string",  "description": "დამტკიცების კომენტარი ბუღალტრისთვის (სურვილისამებრ)"},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "list_pending_drafts",
        "description": "დამტკიცების მოლოდინში მყოფი გატარებების სია.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "მაქსიმალური რაოდენობა (default: 10)"},
            },
        },
    },
    {
        "name": "search_transactions",
        "description": "გატარებების ძებნა — მოვაჭრის სახელით, აღწერით ან ანგარიშის კოდით.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":        {"type": "string", "description": "საძებნი ტექსტი (კომპანია, ტრანზაქციის ტიპი...)"},
                "account_code": {"type": "string", "description": "ანგარიშის კოდი ფილტრისთვის (სურვილისამებრ)"},
                "limit":        {"type": "integer", "description": "მაქსიმალური რაოდენობა (default: 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_account_balance",
        "description": "ანგარიშის სრული ნაშთი — დებეტი, კრედიტი, ბალანსი.",
        "input_schema": {
            "type": "object",
            "properties": {
                "account_code": {"type": "string", "description": "ანგარიშის კოდი (მაგ: 1110, 7510, 3350)"},
                "date_from":    {"type": "string", "description": "დაწყების თარიღი YYYY-MM-DD (სურვილისამებრ)"},
                "date_to":      {"type": "string", "description": "დამთავრების თარიღი YYYY-MM-DD (სურვილისამებრ)"},
            },
            "required": ["account_code"],
        },
    },
    {
        "name": "classify_transaction",
        "description": "ტრანზაქციის კლასიფიკაცია — სადებეტო/საკრედიტო ანგარიშების ავტომატური განსაზღვრა Bridge Hub AI-ით.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "ტრანზაქციის აღწერა"},
                "amount":      {"type": "number", "description": "თანხა (სურვილისამებრ)"},
            },
            "required": ["description"],
        },
    },
]


# ── Tool executors ────────────────────────────────────────────────────────────

async def _tool_create_draft(inp: dict, tenant_id: str) -> dict:
    from app.api.db import get_conn, _q
    try:
        async with get_conn() as conn:
            entry_date = inp.get("date") or date.today().isoformat()
            row = await conn.fetchrow(_q("""
                INSERT INTO journal_drafts
                    (tenant_id, description, amount, debit_account, credit_account,
                     date, source, status, account_code)
                VALUES (%s, %s, %s, %s, %s, %s, 'chat', 'pending', %s)
                RETURNING id, description, amount, debit_account, credit_account, date, status
            """),
                tenant_id, inp["description"], float(inp["amount"]),
                str(inp["debit_account"]), str(inp["credit_account"]),
                entry_date, str(inp["debit_account"]),
            )
            return {
                "success": True,
                "draft_id": row["id"],
                "description": row["description"],
                "amount": float(row["amount"] or 0),
                "debit_account": row["debit_account"],
                "credit_account": row["credit_account"],
                "date": str(row["date"]),
                "status": row["status"],
                "message": f"გატარება #{row['id']} შეიქმნა — PENDING სტატუსით",
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _tool_approve_draft(inp: dict, tenant_id: str) -> dict:
    # P0-1 FIX: AI must NOT approve directly.
    # Direct DB UPDATE was removed. Returns approval_required=True with link to human endpoint.
    # Enforcement chain (period lock, CFO gate, audit log, RBAC, row lock) lives in
    # approval_service.approve_draft_service() — called by the human accountant via POST endpoint.
    try:
        draft_id = int(inp["draft_id"])
    except (KeyError, TypeError, ValueError) as exc:
        return {"success": False, "error": f"draft_id ვალიდური არ არის: {exc}"}
    comment = (inp.get("comment") or "").strip()
    return {
        "approval_required": True,
        "action": "approve_draft",
        "draft_id": draft_id,
        "comment": comment or None,
        "message": (
            "AI ვერ ასრულებს პირდაპირ დამტკიცებას. "
            "ადამიანის (ბუღალტერი / CFO) დამტკიცება საჭიროა."
        ),
        "next_endpoint": f"/api/approval/approve/{draft_id}",
        "next_method": "POST",
        "warning": (
            "დამტკიცება მოითხოვს: period lock check, CFO gate (≥₾10,000), "
            "audit_events ჩანაწერი, RBAC, row-level lock."
        ),
    }


async def _tool_list_pending(inp: dict, tenant_id: str) -> dict:
    from app.api.db import get_conn, _q
    try:
        limit = min(int(inp.get("limit", 10)), 50)
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, description, amount, debit_account, credit_account,
                       TO_CHAR(date, 'YYYY-MM-DD') AS date, status,
                       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS created
                FROM journal_drafts
                WHERE tenant_id = %s AND status IN ('pending', 'PENDING')
                ORDER BY created_at DESC LIMIT %s
            """), tenant_id, limit)]
        return {"success": True, "count": len(rows), "drafts": rows}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _tool_search(inp: dict, tenant_id: str) -> dict:
    from app.api.db import get_conn, _q
    try:
        query = str(inp["query"])
        account_code = inp.get("account_code")
        limit = min(int(inp.get("limit", 10)), 50)
        async with get_conn() as conn:
            if account_code:
                rows = [dict(r) for r in await conn.fetch(_q("""
                    SELECT id, description, amount, debit_account, credit_account,
                           TO_CHAR(date, 'YYYY-MM-DD') AS date, status
                    FROM journal_drafts
                    WHERE tenant_id = %s AND (debit_account = %s OR credit_account = %s OR account_code = %s)
                    ORDER BY created_at DESC LIMIT %s
                """), tenant_id, account_code, account_code, account_code, limit)]
            else:
                rows = [dict(r) for r in await conn.fetch(_q("""
                    SELECT id, description, amount, debit_account, credit_account,
                           TO_CHAR(date, 'YYYY-MM-DD') AS date, status
                    FROM journal_drafts
                    WHERE tenant_id = %s AND description ILIKE %s
                    ORDER BY created_at DESC LIMIT %s
                """), tenant_id, f"%{query}%", limit)]
        return {"success": True, "count": len(rows), "transactions": rows}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _tool_account_balance(inp: dict, tenant_id: str) -> dict:
    from app.api.db import get_conn, _q
    try:
        account_code = str(inp["account_code"])
        date_from = inp.get("date_from")
        date_to = inp.get("date_to")
        conds = [
            "tenant_id = %s",
            "(debit_account = %s OR credit_account = %s OR account_code = %s)",
            "status IN ('approved', 'auto_approved', 'posted', 'APPROVED')",
        ]
        params: list = [tenant_id, account_code, account_code, account_code]
        if date_from:
            conds.append("date >= %s"); params.append(date_from)
        if date_to:
            conds.append("date <= %s"); params.append(date_to)
        async with get_conn() as conn:
            row = await conn.fetchrow(_q(f"""
                SELECT
                    COUNT(*) AS cnt,
                    COALESCE(SUM(CASE WHEN debit_account  = %s THEN amount ELSE 0 END), 0) AS debit_sum,
                    COALESCE(SUM(CASE WHEN credit_account = %s THEN amount ELSE 0 END), 0) AS credit_sum
                FROM journal_drafts
                WHERE {' AND '.join(conds)}
            """), account_code, account_code, *params)
        debit  = float(row["debit_sum"] or 0)
        credit = float(row["credit_sum"] or 0)
        return {
            "success": True,
            "account_code": account_code,
            "entry_count": int(row["cnt"] or 0),
            "debit_total":  round(debit,  2),
            "credit_total": round(credit, 2),
            "balance":      round(debit - credit, 2),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _tool_classify(inp: dict, tenant_id: str) -> dict:
    try:
        from app.knowledge.journal_builder import classify_transaction
        result = classify_transaction(inp["description"], float(inp.get("amount", 0)), tenant_id)
        return {"success": True, "classification": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def _execute_tool(name: str, inp: dict, tenant_id: str) -> dict:
    dispatch = {
        "create_journal_draft": _tool_create_draft,
        "approve_draft":        _tool_approve_draft,
        "list_pending_drafts":  _tool_list_pending,
        "search_transactions":  _tool_search,
        "get_account_balance":  _tool_account_balance,
        "classify_transaction": _tool_classify,
    }
    fn = dispatch.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}
    try:
        return await fn(inp, tenant_id)
    except Exception as e:
        log.error("tool %s error: %s", name, e)
        return {"error": str(e)}


# ── Knowledge context helpers ─────────────────────────────────────────────────

def _fetch_knowledge_context(message: str) -> str:
    try:
        from app.knowledge.knowledge_loader import get_tax_section, get_accounting_section
    except Exception:
        return ""
    msg_lower = message.lower()
    parts = []
    for key, keywords in _TAX_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            s = get_tax_section(key)
            if s:
                parts.append(f"📜 საგადასახადო კოდექსი ({key}):\n{s[:2000]}")
            break
    for key, keywords in _ACC_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            s = get_accounting_section(key)
            if s:
                parts.append(f"📚 ბუღალტრული სტანდარტი ({key}):\n{s[:2000]}")
            break
    return "\n\n".join(parts)


async def _fetch_db_context(message: str, tenant_id: str) -> str:
    try:
        from app.api.db import get_conn, _q
        parts = []
        msg_lower = message.lower()
        async with get_conn() as conn:
            try:
                row = await conn.fetchrow(_q("""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status='approved' OR status='APPROVED') AS approved,
                        COUNT(*) FILTER (WHERE status='pending'  OR status='PENDING')  AS pending,
                        COUNT(*) FILTER (WHERE status='rejected' OR status='REJECTED') AS rejected,
                        COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS inflow,
                        COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS outflow
                    FROM journal_drafts WHERE tenant_id = %s
                """), tenant_id)
                if row:
                    parts.append(
                        f"📊 სისტემის სტატისტიკა:\n"
                        f"  სულ: {row['total']} | დამტკ: {row['approved']} | მოლოდინი: {row['pending']} | უარი: {row['rejected']}\n"
                        f"  შემოსავალი: {float(row['inflow'] or 0):.2f}₾ | გასავალი: {abs(float(row['outflow'] or 0)):.2f}₾"
                    )
            except Exception as e:
                log.warning("unexpected error: %s", e)

            if any(w in msg_lower for w in ["ტრანზაქცი", "დრაფტ", "დოკუმენტ", "ჩანაწერ", "გატარ", "ბოლო", "last", "recent"]):
                try:
                    rows = [dict(r) for r in await conn.fetch(_q("""
                        SELECT id, description, amount, debit_account, credit_account, status,
                               TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS date
                        FROM journal_drafts WHERE tenant_id = %s
                        ORDER BY created_at DESC LIMIT 15
                    """), tenant_id)]
                    if rows:
                        lines = [f"📋 ბოლო {len(rows)} ჩანაწერი:"]
                        for r in rows:
                            lines.append(f"  #{r['id']} [{r['date']}] {r['description'] or '-'} | {float(r['amount'] or 0):.2f}₾ | Dr:{r['debit_account']} Cr:{r['credit_account']} | {r['status']}")
                        parts.append("\n".join(lines))
                except Exception as e:
                    log.warning("unexpected error: %s", e)

            if any(w in msg_lower for w in ["ბანკ", "bank", "გადარ"]):
                try:
                    rows = [dict(r) for r in await conn.fetch(_q("""
                        SELECT bank, date, amount, description FROM bank_transactions
                        WHERE tenant_id = %s ORDER BY date DESC LIMIT 10
                    """), tenant_id)]
                    if rows:
                        lines = [f"🏦 ბანკის ბოლო {len(rows)} ოპ.:"]
                        for r in rows:
                            lines.append(f"  [{r['date']}] {r['bank']} | {float(r['amount'] or 0):.2f}₾ | {r['description'] or '-'}")
                        parts.append("\n".join(lines))
                except Exception as e:
                    log.warning("unexpected error: %s", e)

            if any(w in msg_lower for w in ["თვ", "monthly", "report", "შემოსავ", "გასავ", "cashflow"]):
                try:
                    rows = [dict(r) for r in await conn.fetch(_q("""
                        SELECT TO_CHAR(created_at,'YYYY-MM') AS month, COUNT(*) AS docs,
                            COALESCE(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END),0) AS inflow,
                            COALESCE(SUM(CASE WHEN amount<0 THEN ABS(amount) ELSE 0 END),0) AS outflow
                        FROM journal_drafts WHERE tenant_id = %s
                        GROUP BY 1 ORDER BY 1 DESC LIMIT 6
                    """), tenant_id)]
                    if rows:
                        lines = ["📅 ბოლო თვეები:"]
                        for r in rows:
                            net = float(r['inflow'] or 0) - float(r['outflow'] or 0)
                            lines.append(f"  {r['month']}: {r['docs']} დოკ | +{float(r['inflow'] or 0):.0f}₾ / -{float(r['outflow'] or 0):.0f}₾ | net:{net:.0f}₾")
                        parts.append("\n".join(lines))
                except Exception as e:
                    log.warning("unexpected error: %s", e)

            # ── P0-5: RS.ge document counts ───────────────────────────────────
            try:
                wb_row = await conn.fetchrow(_q(
                    "SELECT COUNT(*) AS cnt FROM waybills WHERE tenant_id = %s"
                ), tenant_id)
                ti_row = await conn.fetchrow(_q(
                    "SELECT COUNT(*) AS cnt FROM tax_invoices WHERE tenant_id = %s"
                ), tenant_id)
                mm_row = await conn.fetchrow(_q(
                    "SELECT COUNT(*) AS cnt FROM triangle_matches "
                    "WHERE tenant_id = %s AND match_status = 'mismatch'"
                ), tenant_id)
                eb_row = await conn.fetchrow(_q(
                    "SELECT COUNT(*) AS cnt FROM evidence_bundles WHERE tenant_id = %s"
                ), tenant_id)
                wb_cnt = int((wb_row or {}).get("cnt") or 0)
                ti_cnt = int((ti_row or {}).get("cnt") or 0)
                mm_cnt = int((mm_row or {}).get("cnt") or 0)
                eb_cnt = int((eb_row or {}).get("cnt") or 0)
                if wb_cnt or ti_cnt or mm_cnt or eb_cnt:
                    parts.append(
                        f"📄 RS.ge დოკუმენტები:\n"
                        f"  ზედნადები: {wb_cnt} | სფ: {ti_cnt} | "
                        f"შეუსაბამობა: {mm_cnt} | evidence bundles: {eb_cnt}"
                    )
            except Exception as _rsge_ctx_err:
                log.debug("rsge context fetch skipped: %s", _rsge_ctx_err)

            # ── P0-5: Period lock status for current month ────────────────────
            try:
                from datetime import date as _today_cls
                _now = _today_cls.today()
                lock_row = await conn.fetchrow(_q("""
                    SELECT 1 FROM period_locks
                    WHERE tenant_id = %s AND period_year = %s
                      AND (period_month = 0 OR period_month = %s)
                      AND unlocked_at IS NULL
                    LIMIT 1
                """), tenant_id, _now.year, _now.month)
                if lock_row is not None:
                    parts.append(
                        f"🔒 PERIOD LOCK: {_now.year}-{_now.month:02d} პერიოდი დახურულია. "
                        "ახალი გატარებები ამ პერიოდში ვერ დაიმტკიცება."
                    )
            except Exception as _pl_ctx_err:
                log.debug("period lock context fetch skipped: %s", _pl_ctx_err)

            # ── P0-5: FX rate availability ────────────────────────────────────
            try:
                fx_row = await conn.fetchrow(_q("""
                    SELECT COUNT(*) AS cnt FROM currency_rates
                    WHERE updated_at >= NOW() - INTERVAL '7 days'
                """))
                if int((fx_row or {}).get("cnt") or 0) == 0:
                    parts.append(
                        "⚠️ FX RATE WARNING: currency_rates ცხრილი ცარიელია ან მოძველებულია (>7 დღე). "
                        "არა-GEL გატარებები ვერ დაიპოსტება სანამ FX კურსი არ განახლდება."
                    )
            except Exception as _fx_ctx_err:
                log.debug("fx rate context fetch skipped: %s", _fx_ctx_err)

        return "\n\n".join(parts)
    except Exception as e:
        log.warning("db context fetch failed: %s", e)
        return ""


def _read_file_text(filename: str, data: bytes) -> str:
    fn = filename.lower()
    try:
        if fn.endswith(".pdf"):
            import fitz
            doc = fitz.open(stream=data, filetype="pdf")
            return "\n".join(doc[i].get_text() for i in range(min(len(doc), 20)))
        if fn.endswith(".docx"):
            import docx
            doc = docx.Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        if fn.endswith(".csv"):
            return data.decode("utf-8", errors="replace")[:10000]
        if fn.endswith((".xlsx", ".xls")):
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True)
            lines = []
            for ws in wb.worksheets[:3]:
                for row in ws.iter_rows(max_row=200, values_only=True):
                    lines.append("\t".join(str(c or "") for c in row))
            return "\n".join(lines)
    except Exception as e:
        log.warning("file parse error %s: %s", filename, e)
    return f"[ფაილი: {filename} — ტექსტი ვერ წაიკითხა]"


# ── Main chat endpoint ────────────────────────────────────────────────────────

@router.post("/chat")
async def claude_chat(
    request: Request,
    message: str = Form(""),
    history: str = Form("[]"),
    file: UploadFile = File(None),
):
    require_permission(request, "chat:use")
    message = (message or "").strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return http_error(503, "ANTHROPIC_API_KEY არ არის კონფიგურირებული.", "SERVICE_UNAVAILABLE")

    tenant_id = getattr(request.state, "tenant_id", None) or "default"

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)

        try:
            hist = json.loads(history) if history else []
        except Exception:
            hist = []

        db_context = await _fetch_db_context(message, tenant_id)
        kb_context = _fetch_knowledge_context(message)

        system = SYSTEM_PROMPT
        if kb_context:
            system += f"\n\n--- Bridge Hub ცოდნის ბაზა ---\n{kb_context}\n---"
        if db_context:
            system += f"\n\n--- Bridge Hub-ის მიმდინარე მონაცემები ---\n{db_context}\n---"

        messages = []
        for h in hist[-16:]:
            role = "user" if h.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": h.get("text", "")})

        content_parts = []
        if file:
            raw = await file.read()
            file_text = _read_file_text(file.filename, raw)
            content_parts.append({"type": "text", "text": f"📎 ფაილი: {file.filename}\n\n{file_text[:14000]}"})

        user_text = message or ("გაანალიზე ეს ფაილი" if file else "გამარჯობა")
        content_parts.append({"type": "text", "text": user_text})
        messages.append({"role": "user", "content": content_parts})

        # ── First call (may return tool_use) ─────────────────────────────
        resp = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4000,
            system=system,
            tools=TOOLS,
            messages=messages,
            timeout=30.0,
        )

        tools_used = []

        # ── Tool use loop (max 3 rounds to avoid runaway) ─────────────────
        for _round in range(3):
            if resp.stop_reason != "tool_use":
                break

            # Execute every tool Claude requested
            tool_results = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                log.info("chat tool_use: %s %s", block.name, block.input)
                result = await _execute_tool(block.name, block.input, tenant_id)
                tools_used.append({"tool": block.name, "result": result})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

            # Append assistant turn + tool results, then call Claude again
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user",      "content": tool_results})

            resp = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4000,
                system=system,
                tools=TOOLS,
                messages=messages,
                timeout=30.0,
            )

        # Extract final text answer
        answer = next(
            (block.text for block in resp.content if hasattr(block, "text")),
            "პასუხი ვერ მივიღე."
        )

        return {
            "ok": True,
            "answer": answer,
            "model": "claude-sonnet-4-6",
            "had_context": bool(db_context or kb_context),
            "tools_used": tools_used,
        }

    except Exception as e:
        log.error("claude_chat error: %s", e)
        return http_error(503, "AI temporarily unavailable. Please try again.", "SERVICE_UNAVAILABLE")
