"""
Bridge Hub — Direct Claude Chat with full DB context
/api/claude/chat  →  Claude Sonnet sees all Bridge Hub data
"""
import os
import io
import json
import logging
from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/claude", tags=["Claude Chat"])

# Knowledge keyword map → section keys
_TAX_KEYWORDS = {
    "vat": ["დღგ", "vat", "დღგ-ს", "დღგ-ის"],
    "pit": ["საშემოსავლო", "pit", "income tax", "personal"],
    "cit": ["მოგების", "cit", "profit tax", "corporate"],
    "withholding": ["წყაროსთან", "withholding", "retention"],
    "property": ["ქონება", "property tax"],
    "penalty": ["სანქცი", "penalty", "fine", "ჯარიმ"],
    "non_resident": ["არარეზიდენტ", "non-resident", "foreign"],
    "micro": ["მცირე ბიზნეს", "micro", "small business"],
}
_ACC_KEYWORDS = {
    "salary": ["ხელფას", "salary", "payroll", "payg", "შრომ"],
    "dividends": ["დივიდენდ", "dividend"],
    "depreciation": ["ამორტიზაც", "depreciation"],
    "fixed_assets": ["ძირითადი საშუალებ", "fixed asset", "სიმდიდრ"],
    "inventory": ["მარაგ", "inventory", "stock"],
    "receivables": ["მოთხოვნ", "receivable", "debtor"],
    "payables": ["ვალდებულ", "payable", "creditor"],
    "loan": ["სესხ", "loan", "credit"],
    "capital": ["კაპიტალ", "capital", "equity"],
    "principles": ["პრინციპ", "principle", "standard", "ifrs", "gaap"],
}


def _fetch_knowledge_context(message: str) -> str:
    """Pull relevant sections from loaded knowledge files based on message content."""
    try:
        from app.knowledge.knowledge_loader import get_tax_section, get_accounting_section
    except Exception:
        return ""

    msg_lower = message.lower()
    parts = []

    for key, keywords in _TAX_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            section = get_tax_section(key)
            if section:
                parts.append(f"📜 საგადასახადო კოდექსი ({key}):\n{section[:2000]}")
            break  # one tax section per message to avoid token bloat

    for key, keywords in _ACC_KEYWORDS.items():
        if any(kw in msg_lower for kw in keywords):
            section = get_accounting_section(key)
            if section:
                parts.append(f"📚 ბუღალტრული სტანდარტი ({key}):\n{section[:2000]}")
            break

    return "\n\n".join(parts)

SYSTEM_PROMPT = """\
შენ ხარ Bridge Hub AI — ქართული ფინანსური OS-ის ჭკვიანი ასისტენტი.
შენ მუშაობ ისევე როგორც Claude — სრულყოფილი, გარჩეული, ნებისმიერ კითხვაზე პასუხობ.

შენი ექსპერტიზა:
• ქართული საგადასახადო კოდექსი — დღგ 18%, საშემოსავლო 20%, მოგების 15%, სოციალური 2%
• IFRS/GAAP ბუღალტრული სტანდარტები
• ჟურნალის ჩანაწერები, COA (ანგარიშთა გეგმა)
• ხელფასი, დივიდენდი, ამორტიზაცია, VAT
• ფინანსური ანგარიშები — ბალანსი, მოგება-ზარალი, ფულის ნაკადი
• ბანკის ამონაწერი, რეკონსილიაცია
• ნებისმიერი ზოგადი კითხვა — ისტორია, მათემატიკა, პროგრამირება, კანონი...

როდესაც კონტექსტი (DB მონაცემები) მოგეწოდება, გამოიყენე სრულყოფილი ანალიზისთვის.
პასუხი გასცე ქართულად, სრულად და გარჩეულად — ისე როგორც Claude მუშაობს.
"""


def _fetch_db_context(message: str, tenant_id: str) -> str:
    """Fetch relevant data from DB based on the question."""
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor

        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            return ""

        conn = psycopg2.connect(database_url)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        parts = []
        msg_lower = message.lower()

        # Always fetch overview stats
        try:
            cur.execute("""
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status='APPROVED') AS approved,
                    COUNT(*) FILTER (WHERE status='PENDING') AS pending,
                    COUNT(*) FILTER (WHERE status='REJECTED') AS rejected,
                    COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS inflow,
                    COALESCE(SUM(CASE WHEN amount < 0 THEN amount ELSE 0 END), 0) AS outflow
                FROM journal_drafts
                WHERE tenant_id = %s
            """, (tenant_id,))
            row = cur.fetchone()
            if row:
                parts.append(
                    f"📊 სისტემის სტატისტიკა:\n"
                    f"  სულ დოკუმენტი: {row['total']}\n"
                    f"  დამტკიცებული: {row['approved']}, მოლოდინში: {row['pending']}, უარყოფილი: {row['rejected']}\n"
                    f"  შემოსავალი: {float(row['inflow'] or 0):.2f} ₾, გასავალი: {abs(float(row['outflow'] or 0)):.2f} ₾"
                )
        except Exception:
            pass

        # If asking about transactions/drafts/documents
        if any(w in msg_lower for w in ["ტრანზაქცი", "დრაფტ", "დოკუმენტ", "ჩანაწერ", "გატარ", "ბოლო", "ბარათ", "last", "recent"]):
            try:
                cur.execute("""
                    SELECT id, description, amount, account_code, status,
                           debit_account, credit_account,
                           TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI') AS date
                    FROM journal_drafts
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC LIMIT 15
                """, (tenant_id,))
                rows = cur.fetchall()
                if rows:
                    lines = [f"📋 ბოლო {len(rows)} ტრანზაქცია:"]
                    for r in rows:
                        lines.append(
                            f"  [{r['date']}] {r['description'] or '-'} | "
                            f"{float(r['amount'] or 0):.2f}₾ | {r['account_code'] or '-'} | {r['status']}"
                        )
                    parts.append("\n".join(lines))
            except Exception:
                pass

        # If asking about bank transactions
        if any(w in msg_lower for w in ["ბანკ", "bank", "გადარ", "ანგარიშ"]):
            try:
                cur.execute("""
                    SELECT bank, date, amount, description
                    FROM bank_transactions
                    WHERE tenant_id = %s
                    ORDER BY date DESC LIMIT 15
                """, (tenant_id,))
                rows = cur.fetchall()
                if rows:
                    lines = [f"🏦 ბანკის ბოლო {len(rows)} ოპერაცია:"]
                    for r in rows:
                        lines.append(
                            f"  [{r['date']}] {r['bank']} | {float(r['amount'] or 0):.2f}₾ | {r['description'] or '-'}"
                        )
                    parts.append("\n".join(lines))
            except Exception:
                pass

        # If asking about learning/rules/classification
        if any(w in msg_lower for w in ["ნასწავლ", "pattern", "კლასიფ", "წესი", "rule", "learn"]):
            try:
                cur.execute("""
                    SELECT pattern_value, account_code, reason, confidence_score, source
                    FROM learning_patterns
                    WHERE tenant_id IN (%s, 'global') AND status = 'active'
                    ORDER BY confidence_score DESC LIMIT 20
                """, (tenant_id,))
                rows = cur.fetchall()
                if rows:
                    lines = [f"🧠 ნასწავლი {len(rows)} წესი:"]
                    for r in rows:
                        lines.append(
                            f"  '{r['pattern_value']}' → {r['account_code']} "
                            f"(confidence: {float(r['confidence_score'] or 0):.0%}, {r['source']})"
                        )
                    parts.append("\n".join(lines))
            except Exception:
                pass

        # Monthly summary if asked
        if any(w in msg_lower for w in ["თვ", "monthly", "ანგარიშ", "report", "შემოსავ", "გასავ", "cashflow"]):
            try:
                cur.execute("""
                    SELECT
                        TO_CHAR(created_at, 'YYYY-MM') AS month,
                        COUNT(*) AS docs,
                        COALESCE(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 0) AS inflow,
                        COALESCE(SUM(CASE WHEN amount < 0 THEN ABS(amount) ELSE 0 END), 0) AS outflow
                    FROM journal_drafts
                    WHERE tenant_id = %s
                    GROUP BY 1 ORDER BY 1 DESC LIMIT 6
                """, (tenant_id,))
                rows = cur.fetchall()
                if rows:
                    lines = ["📅 ბოლო თვეების შეჯამება:"]
                    for r in rows:
                        net = float(r['inflow'] or 0) - float(r['outflow'] or 0)
                        lines.append(
                            f"  {r['month']}: {r['docs']} დოკ | "
                            f"+{float(r['inflow'] or 0):.0f}₾ / -{float(r['outflow'] or 0):.0f}₾ | net: {net:.0f}₾"
                        )
                    parts.append("\n".join(lines))
            except Exception:
                pass

        cur.close()
        conn.close()
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


@router.post("/chat")
async def claude_chat(
    request: Request,
    message: str = Form(""),
    history: str = Form("[]"),
    file: UploadFile = File(None),
):
    message = (message or "").strip()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return JSONResponse(status_code=503, content={"ok": False, "answer": "ANTHROPIC_API_KEY არ არის კონფიგურირებული."})

    tenant_id = getattr(request.state, "tenant_id", None) or "default"

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)

        # Parse conversation history
        try:
            hist = json.loads(history) if history else []
        except Exception:
            hist = []

        # Fetch DB context + knowledge file context
        db_context = _fetch_db_context(message, tenant_id)
        kb_context = _fetch_knowledge_context(message)

        # Build system with live DB data + knowledge files
        system = SYSTEM_PROMPT
        if kb_context:
            system += f"\n\n--- Bridge Hub ცოდნის ბაზა (საგადასახადო/ბუღალტრული ფაილები) ---\n{kb_context}\n---"
        if db_context:
            system += f"\n\n--- Bridge Hub-ის მიმდინარე მონაცემები ---\n{db_context}\n---"

        # Build messages
        messages = []
        for h in hist[-16:]:
            role = "user" if h.get("role") == "user" else "assistant"
            text = h.get("text", "")
            # strip file prefix from stored messages
            if text.startswith("📎"):
                text = text
            messages.append({"role": role, "content": text})

        # Current user turn
        content_parts = []
        if file:
            raw = await file.read()
            file_text = _read_file_text(file.filename, raw)
            content_parts.append({"type": "text", "text": f"📎 ფაილი: {file.filename}\n\n{file_text[:14000]}"})

        user_text = message or ("გაანალიზე ეს ფაილი" if file else "გამარჯობა")
        content_parts.append({"type": "text", "text": user_text})
        messages.append({"role": "user", "content": content_parts})

        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=system,
            messages=messages,
        )

        answer = resp.content[0].text if resp.content else "პასუხი ვერ მივიღე."
        return {"ok": True, "answer": answer, "model": "claude-sonnet-4-6", "had_context": bool(db_context or kb_context)}

    except Exception as e:
        log.error("claude_chat error: %s", e)
        return JSONResponse(status_code=500, content={"ok": False, "answer": f"შეცდომა: {e}"})
