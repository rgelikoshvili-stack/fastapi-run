import re
from pathlib import Path

MAIN = Path("main.py")
s = MAIN.read_text(encoding="utf-8")

changed = False

def insert_before_app_imports(text: str) -> str:
    global changed
    if "app = FastAPI" not in text:
        print("[!] ვერ ვიპოვე 'app = FastAPI' — patch ვერ გაკეთდა.")
        return text

    # check if Optional/Tuple already imported from typing
    has_optional = bool(re.search(r"from\s+typing\s+import\s+.*\bOptional\b", text))
    has_tuple = bool(re.search(r"from\s+typing\s+import\s+.*\bTuple\b", text))

    add = []
    if "import re" not in text:
        add.append("import re\n")
    if "import hashlib" not in text:
        add.append("import hashlib\n")
    if "BaseModel" not in text:
        add.append("from pydantic import BaseModel\n")
    if not has_optional:
        add.append("from typing import Optional\n")
    if not has_tuple:
        add.append("from typing import Tuple\n")

    if not add:
        return text

    marker = "# BEGIN EMAIL_INVOICE_IMPORTS\n"
    if marker in text:
        return text

    block = marker + "".join(add) + "# END EMAIL_INVOICE_IMPORTS\n\n"
    idx = text.find("app = FastAPI")
    text = text[:idx] + block + text[idx:]
    changed = True
    return text

EI_BLOCK_MARKER = "# BEGIN EMAIL_INVOICE_BLOCK\n"

def insert_email_invoice_block(text: str) -> str:
    global changed
    if EI_BLOCK_MARKER in text:
        return text

    # insert after the line containing "app = FastAPI("
    m = re.search(r"^app\s*=\s*FastAPI\(.*\)\s*$", text, flags=re.MULTILINE)
    if not m:
        # fallback: first occurrence line with 'app = FastAPI'
        pos = text.find("app = FastAPI")
        if pos == -1:
            print("[!] app = FastAPI ვერ ვიპოვე — email_invoice block ვერ ჩაჯდა.")
            return text
        line_end = text.find("\n", pos)
        insert_at = line_end + 1 if line_end != -1 else len(text)
    else:
        insert_at = m.end() + 1  # after that line's newline

    block = f"""{EI_BLOCK_MARKER}
# -----------------------------
# Email Invoice (offline-ready)
# -----------------------------

_EI_TOTAL_HINT_RE = re.compile(
    r"\\b("
    r"total|amount\\s*due|grand\\s*total|balance\\s*due|invoice\\s*total|total\\s*due|payable|to\\s*pay|sum|"
    r"ჯამი|სულ|საერთო\\s*ჯამი|სულ\\s*გადასახდელი|გადასახდელია|"
    r"totale|importo|da\\s*pagare|saldo"
    r")\\b",
    re.IGNORECASE
)

_EI_AMOUNT_RE = re.compile(
    r"(?:(EUR|USD|GEL)\\s*)?([€$₾]?\\s*\\d[\\d\\s.,]*\\d)(?:\\s*(EUR|USD|GEL))?",
    re.IGNORECASE
)

def _ei_sha1(s: str) -> str:
    import hashlib as _hashlib
    return _hashlib.sha1((s or "").encode("utf-8")).hexdigest()

def _ei_preview(s: str, n: int = 220) -> str:
    s = (s or "").replace("\\r", " ").replace("\\n", " ")
    return s[:n]

def _ei_guess_currency(text: str) -> Optional[str]:
    t = (text or "").upper()
    if "€" in (text or "") or " EUR" in t or t.startswith("EUR"):
        return "EUR"
    if "$" in (text or "") or " USD" in t or t.startswith("USD"):
        return "USD"
    if "₾" in (text or "") or " GEL" in t or t.startswith("GEL"):
        return "GEL"
    return None

def _ei_parse_amount(num_text: str) -> Optional[float]:
    if not num_text:
        return None
    s = num_text.strip()
    s = s.replace("€", "").replace("$", "").replace("₾", "")
    s = s.replace(" ", "")

    # 1,234.56  vs  1.234,56  vs 150,00
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." not in s:
        tail = s.split(",")[-1]
        if len(tail) in (2, 3):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")

    try:
        return float(s)
    except Exception:
        return None

def _ei_guess_vendor(from_field: Optional[str], subject: Optional[str]) -> Optional[str]:
    if from_field:
        name = from_field.split("<")[0].strip().strip('"').strip()
        if name and "no-reply" not in name.lower() and "noreply" not in name.lower():
            return name[:80]
    if subject:
        m = re.search(r"invoice\\s+from\\s+(.+)$", subject, re.IGNORECASE)
        if m:
            return m.group(1).strip()[:80]
    return None

def _ei_extract_amount_currency_heuristic(body: str) -> Tuple[Optional[float], Optional[str], str]:
    text = body or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    for ln in lines[:200]:
        if _EI_TOTAL_HINT_RE.search(ln):
            m = _EI_AMOUNT_RE.search(ln)
            if m:
                c1, num, c2 = m.group(1), m.group(2), m.group(3)
                cur = (c1 or c2) or _ei_guess_currency(ln) or _ei_guess_currency(text)
                amt = _ei_parse_amount(num)
                if amt is not None:
                    return amt, cur, "total_line"

    m = _EI_AMOUNT_RE.search(text)
    if m:
        c1, num, c2 = m.group(1), m.group(2), m.group(3)
        cur = (c1 or c2) or _ei_guess_currency(text)
        amt = _ei_parse_amount(num)
        if amt is not None:
            return amt, cur, "global_match"

    return None, None, "none"

def _ei_json_from_text(s: str) -> dict:
    import json as _json
    s = (s or "").strip()
    if not s:
        return {{}}
    try:
        return _json.loads(s)
    except Exception:
        m = re.search(r"\\{{.*\\}}", s, re.DOTALL)
        if m:
            try:
                return _json.loads(m.group(0))
            except Exception:
                return {{}}
        return {{}}

def _ei_llm_extract(from_field: Optional[str], subject: Optional[str], body: str, trace_id: str) -> dict:
    import os as _os
    api_key = _os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {{}}

    model = _os.getenv("OPENAI_MODEL", "gpt-5-mini")
    sys_prompt = (
        "Extract invoice fields from this email. "
        "Return JSON only: {{\\"vendor\\": string|null, \\"amount\\": number|null, \\"currency\\": \\"EUR\\"|\\"USD\\"|\\"GEL\\"|null}}. "
        "No extra text."
    )
    user_text = f"FROM: {{from_field}}\\nSUBJECT: {{subject}}\\nBODY:\\n{{body}}\\n"

    try:
        from openai import OpenAI  # type: ignore
        client = OpenAI(api_key=api_key)

        # Responses API first
        try:
            resp = client.responses.create(
                model=model,
                input=[
                    {{"role": "system", "content": sys_prompt}},
                    {{"role": "user", "content": user_text}},
                ],
            )
            data = _ei_json_from_text(getattr(resp, "output_text", "") or "")
            if isinstance(data, dict) and data:
                data["source"] = "llm"
                return data
        except Exception:
            pass

        # Chat Completions fallback
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {{"role": "system", "content": sys_prompt}},
                    {{"role": "user", "content": user_text}},
                ],
            )
            content = resp.choices[0].message.content if resp and resp.choices else ""
            data = _ei_json_from_text(content or "")
            if isinstance(data, dict) and data:
                data["source"] = "llm"
                return data
        except Exception:
            pass

        return {{}}
    except Exception as e:
        try:
            _log("bridge.email_invoice.llm_error", trace_id, {{"err": str(e)[:200]}})
        except Exception:
            pass
        return {{}}

def _ei_classify_email_invoice(payload: dict, trace_id: str) -> dict:
    from_field = payload.get("from") or payload.get("from_field") or payload.get("sender") or payload.get("from_email")
    subject = payload.get("subject")
    body = payload.get("body") or payload.get("text") or payload.get("content") or ""
    body = str(body)

    vendor_h = _ei_guess_vendor(from_field, subject)
    amount_h, currency_h, reason = _ei_extract_amount_currency_heuristic(body)

    try:
        _log("bridge.email_invoice.heuristic", trace_id, {{
            "vendor": vendor_h,
            "amount": amount_h,
            "currency": currency_h,
            "reason": reason,
            "body_len": len(body),
            "body_sha1": _ei_sha1(body),
            "preview": _ei_preview(body),
        }})
    except Exception:
        pass

    vendor, amount, currency = vendor_h, amount_h, currency_h
    source = "heuristic"

    if vendor is None or amount is None or currency is None:
        llm = _ei_llm_extract(from_field, subject, body, trace_id)
        if llm:
            vendor = vendor or llm.get("vendor")
            amount = amount if amount is not None else llm.get("amount")
            currency = currency or llm.get("currency")
            source = "hybrid"

        try:
            _log("bridge.email_invoice.merged", trace_id, {{
                "source": source,
                "vendor": vendor,
                "amount": amount,
                "currency": currency,
            }})
        except Exception:
            pass

    return {{
        "task_type": "email_invoice",
        "vendor": vendor,
        "amount": amount,
        "currency": currency,
        "source": source,
    }}

class DemoEmailInvoice(BaseModel):
    from_field: Optional[str] = None
    subject: Optional[str] = None
    body: str

@app.post("/bridge/demo/email_invoice")
async def demo_email_invoice(req: DemoEmailInvoice):
    trace_id = _ei_sha1((req.from_field or "") + "|" + (req.subject or "") + "|" + (req.body or ""))[:16]
    payload = {{"from": req.from_field, "subject": req.subject, "text": req.body}}
    result = _ei_classify_email_invoice(payload, trace_id)
    return {{"ok": True, "trace_id": trace_id, "result": result}}

# END EMAIL_INVOICE_BLOCK
"""

    text = text[:insert_at] + block + text[insert_at:]
    changed = True
    return text

CLASSIFY_MARKER = "# BEGIN EMAIL_INVOICE_CLASSIFY_BRANCH\n"

def insert_classify_branch(text: str) -> str:
    global changed
    if CLASSIFY_MARKER in text:
        return text

    lines = text.splitlines(True)

    # find decorator
    dec_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().startswith('@app.post') and '"/bridge/classify"' in ln.replace("'", '"'):
            dec_idx = i
            break
    if dec_idx is None:
        print("[!] ვერ ვიპოვე @app.post(\"/bridge/classify\") — classify branch ვერ ჩაჯდა.")
        return text

    # find def line after decorator
    def_idx = None
    for j in range(dec_idx + 1, min(dec_idx + 20, len(lines))):
        if lines[j].lstrip().startswith("async def") or lines[j].lstrip().startswith("def"):
            def_idx = j
            break
    if def_idx is None:
        print("[!] classify decorator-ის შემდეგ def ვერ ვიპოვე.")
        return text

    base_indent = len(lines[def_idx]) - len(lines[def_idx].lstrip())
    body_indent = base_indent + 4

    # scan until function ends
    end_idx = def_idx + 1
    for k in range(def_idx + 1, len(lines)):
        ln = lines[k]
        if ln.strip() == "":
            continue
        indent = len(ln) - len(ln.lstrip())
        if indent <= base_indent and not ln.lstrip().startswith("#"):
            end_idx = k
            break
    else:
        end_idx = len(lines)

    # find insertion point after task_type/payload/trace_id assignments if present
    insert_at = def_idx + 1
    candidates = []

    for k in range(def_idx + 1, end_idx):
        t = lines[k].strip()
        if re.match(r"task_type\s*=", t):
            candidates.append(k)
        if re.match(r"payload\s*=", t) or re.match(r"data\s*=", t):
            candidates.append(k)
        if re.match(r"trace_id\s*=", t):
            candidates.append(k)

    if candidates:
        insert_at = max(candidates) + 1
    else:
        # if we can't find task_type, don't risk breaking handler
        print("[!] classify handler-ში task_type/payload/trace_id assignment ვერ ვიპოვე — branch ავტომატურად არ ჩავსვი.")
        return text

    indent = " " * body_indent
    block = (
        f"{indent}{CLASSIFY_MARKER}"
        f"{indent}if task_type == \"email_invoice\":\n"
        f"{indent}    result = _ei_classify_email_invoice(payload, trace_id)\n"
        f"{indent}    return {{\"ok\": True, \"trace_id\": trace_id, \"result\": result}}\n"
        f"{indent}# END EMAIL_INVOICE_CLASSIFY_BRANCH\n"
    )

    lines.insert(insert_at, block)
    changed = True
    return "".join(lines)

s2 = s
s2 = insert_before_app_imports(s2)
s2 = insert_email_invoice_block(s2)
s2 = insert_classify_branch(s2)

if changed:
    MAIN.write_text(s2, encoding="utf-8")
    print("[OK] main.py დაპაჩდა (imports + email_invoice block + demo endpoint + classify attempt).")
else:
    print("[OK] ცვლილება არ იყო საჭირო (ან marker-ები უკვე არსებობდა).")
