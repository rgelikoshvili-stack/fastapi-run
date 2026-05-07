"""
app/api/services/ocr_service.py
Bridge Hub — Invoice OCR Service
Claude Vision (primary) + doc_analyzer (fallback) + duplicate detection
"""
import re
import json
import base64
import os
import time
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Optional
from app.api.doc_analyzer import analyze, to_dict
from app.api.metrics import AI_CLASSIFICATION_TOTAL, AI_CLASSIFICATION_DURATION


# ---------------------------------------------------------------------------
# Claude Vision OCR (primary extractor)
# ---------------------------------------------------------------------------

def _pdf_first_page_png(file_bytes: bytes) -> Optional[bytes]:
    try:
        import fitz
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2, 2))
        return pix.tobytes("png")
    except Exception:
        return None


def _extract_with_claude_vision(file_bytes: bytes, filename: str) -> Optional[dict]:
    """Claude Haiku Vision — structured invoice extraction."""
    try:
        import anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            return None

        fname_lower = (filename or "").lower()
        image_data: Optional[str] = None
        media_type = "image/png"

        if fname_lower.endswith(".pdf") or file_bytes[:4] == b"%PDF":
            png = _pdf_first_page_png(file_bytes)
            if not png:
                return None
            image_data = base64.b64encode(png).decode()
        elif fname_lower.endswith((".png",)):
            image_data = base64.b64encode(file_bytes).decode()
        elif fname_lower.endswith((".jpg", ".jpeg")):
            image_data = base64.b64encode(file_bytes).decode()
            media_type = "image/jpeg"
        else:
            return None

        if not image_data:
            return None

        client = anthropic.Anthropic(api_key=api_key)
        _t0 = time.time()
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a Georgian invoice (ინვოისი/ანგარიშ-ფაქტურა). "
                            "Extract these fields and return ONLY valid JSON, nothing else:\n"
                            '{"invoice_number":null,"date":null,"seller":null,"total_amount":null,"net_amount":null,"vat_amount":null,"currency":"GEL"}\n\n'
                            "Rules:\n"
                            "- seller = the company at the TOP of the invoice / მიმღები (who receives payment / service provider). "
                            "  Read the Georgian text EXACTLY as printed — do NOT translate or guess.\n"
                            "- total_amount = სულ გადასახდელი / ჯამი / grand total including VAT\n"
                            "- net_amount = total excluding VAT (დღგ-ს გარეშე / დღგ გარეშე)\n"
                            "- vat_amount = დღგ / VAT amount only\n"
                            "- date format: YYYY-MM-DD\n"
                            "- currency: GEL, USD, or EUR only\n"
                            "- Copy Georgian text character-by-character — do NOT hallucinate or paraphrase.\n"
                            "- Use null for unknown fields\n"
                            "Return ONLY the JSON object, no explanation."
                        ),
                    },
                ],
            }],
        )

        raw = resp.content[0].text.strip()
        m = re.search(r'\{[\s\S]*?\}', raw)
        if not m:
            return None
        data = json.loads(m.group())
        elapsed = time.time() - _t0
        # Validate at least one numeric field
        if data.get("total_amount") or data.get("net_amount"):
            AI_CLASSIFICATION_TOTAL.labels(tenant="ocr", result="success").inc()
            AI_CLASSIFICATION_DURATION.labels(model="claude-haiku-4-5-20251001").observe(elapsed)
            return data
        AI_CLASSIFICATION_TOTAL.labels(tenant="ocr", result="fallback").inc()
        return None

    except Exception:
        AI_CLASSIFICATION_TOTAL.labels(tenant="ocr", result="failure").inc()
        return None


# ---------------------------------------------------------------------------
# Main extractor — Vision first, doc_analyzer fallback
# ---------------------------------------------------------------------------

def extract_invoice_fields(filename: str, data: bytes) -> dict:
    vision = _extract_with_claude_vision(data, filename)

    if vision:
        amount = _safe_float(vision.get("total_amount"))
        net_amount = _safe_float(vision.get("net_amount"))
        vat_amount = _safe_float(vision.get("vat_amount"))
        currency = vision.get("currency") or "GEL"
        date_raw = vision.get("date")
        date = _parse_date(str(date_raw)) if date_raw else None
        partner = (vision.get("seller") or "")[:100] or None
        invoice_number = vision.get("invoice_number")

        # Derive missing values
        if amount and not net_amount and vat_amount:
            net_amount = round(amount - vat_amount, 2)
        elif amount and not vat_amount and not net_amount:
            _amt = Decimal(str(amount))
            _vat = (_amt * Decimal("0.18") / Decimal("1.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            vat_amount = float(_vat)
            net_amount = float((_amt - _vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        elif amount and net_amount and not vat_amount:
            vat_amount = round(amount - net_amount, 2)

        # Fallback to doc_analyzer for IBAN/ids if needed
        result = analyze(filename, data)
        fields = to_dict(result)
        _ibans = fields.get("ibans") or []
        iban = _ibans[0] if _ibans else None

        return {
            "ok": True,
            "filename": filename,
            "doc_format": fields.get("doc_format"),
            "ocr_used": True,
            "ocr_engine": "claude_vision",
            "invoice_number": str(invoice_number) if invoice_number else None,
            "date": date,
            "amount": amount,
            "currency": currency,
            "vat_amount": vat_amount,
            "net_amount": net_amount if net_amount is not None else amount,
            "partner": partner,
            "iban": iban,
            "warnings": fields.get("warnings", []),
            "raw_amounts": fields.get("amounts", [])[:5],
            "raw_dates": fields.get("dates", [])[:5],
        }

    # ---- Fallback: doc_analyzer ----
    result = analyze(filename, data)
    fields = to_dict(result)

    amount = None
    currency = "GEL"
    amounts = fields.get("amounts", [])
    if amounts:
        largest = max(amounts, key=lambda x: x.get("value", 0))
        amount = largest.get("value")
        currency = largest.get("currency") or "GEL"

    date = None
    dates = fields.get("dates", [])
    if dates:
        date = _parse_date(dates[0])

    partner = None
    names = fields.get("names", [])
    if names:
        partner = names[0][:100]

    invoice_number = _extract_invoice_number(fields.get("ids", []))

    iban = None
    ibans = fields.get("ibans", [])
    if ibans:
        iban = ibans[0]

    vat_amount = None
    net_amount = None
    if amount:
        _amt = Decimal(str(amount))
        _vat = (_amt * Decimal("0.18") / Decimal("1.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        vat_amount = float(_vat)
        net_amount = float((_amt - _vat).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return {
        "ok": True,
        "filename": filename,
        "doc_format": fields.get("doc_format"),
        "ocr_used": fields.get("ocr_used", False),
        "ocr_engine": "doc_analyzer",
        "invoice_number": invoice_number,
        "date": date,
        "amount": amount,
        "currency": currency,
        "vat_amount": vat_amount,
        "net_amount": net_amount if net_amount is not None else amount,
        "partner": partner,
        "iban": iban,
        "warnings": fields.get("warnings", []),
        "raw_amounts": amounts[:5],
        "raw_dates": dates[:5],
    }


# ---------------------------------------------------------------------------
# Draft creation with VAT line breakdown
# ---------------------------------------------------------------------------

def create_draft_from_invoice(
    invoice_fields: dict,
    tenant_id: str = "default",
    source_type: str = "invoice_ocr",
    force: bool = False,
) -> dict:
    """
    OCR შედეგიდან journal draft-ის შექმნა.
    VAT > 0 → 3-line journal_entries (net Dr 7110 + VAT Dr 1430 + total Cr 3310).
    force=True — duplicate-ის შემთხვევაშიც ქმნის ახალ draft-ს.
    """
    from app.api.db import get_db
    import psycopg2.extras

    amount = invoice_fields.get("amount")
    if not amount:
        return {"ok": False, "error": "თანხა ვერ ამოიღო ინვოისიდან"}

    partner = invoice_fields.get("partner") or ""
    date = invoice_fields.get("date") or datetime.now().strftime("%Y-%m-%d")
    vat_amount = invoice_fields.get("vat_amount")
    net_amount = invoice_fields.get("net_amount") or amount

    _inv_num = invoice_fields.get("invoice_number")
    _inv_num = str(_inv_num) if (_inv_num and str(_inv_num).lower() not in ("none", "null", "")) else None
    _partner = partner.strip() if partner and partner.lower() not in ("none", "null") else None

    if _inv_num and _partner:
        description = f"Invoice {_inv_num} — {_partner}"
    elif _partner:
        description = f"Invoice — {_partner}"
    elif _inv_num:
        description = f"Invoice #{_inv_num}"
    else:
        description = "Invoice (OCR)"

    from app.policy.localization.georgia_pack import get_account
    _desc_lower = description.lower()
    _partner_lower = (partner or "").lower()
    _combined = _desc_lower + " " + _partner_lower
    if any(k in _combined for k in ["communal", "კომუნალ", "electricity", "water", "gas", "გაზი", "elektro"]):
        debit_account = "7210"
    elif any(k in _combined for k in ["payroll", "salary", "ხელფასი", "wages"]):
        debit_account = "6100"
    elif any(k in _combined for k in ["rent", "იჯარა", "lease", "ქირა"]):
        debit_account = "7220"
    elif any(k in _combined for k in ["transport", "delivery", "მიტანა", "courier", "logistics"]):
        debit_account = "7130"
    else:
        debit_account = get_account("cost_of_service") or "7110"
    credit_account = get_account("accounts_payable") or "3310"

    # Build journal_entries JSONB for VAT breakdown
    journal_entries = None
    if vat_amount and vat_amount > 0 and net_amount and net_amount > 0:
        journal_entries = json.dumps([
            {
                "line": 1,
                "debit_account": debit_account,
                "credit_account": None,
                "amount": round(float(net_amount), 2),
                "description": f"Net expense — {description}",
            },
            {
                "line": 2,
                "debit_account": "1430",
                "credit_account": None,
                "amount": round(float(vat_amount), 2),
                "description": "Input VAT (დღგ)",
            },
            {
                "line": 3,
                "debit_account": None,
                "credit_account": credit_account,
                "amount": round(float(amount), 2),
                "description": "Accounts payable — total",
            },
        ])

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        if not force:
            cur.execute("""
                SELECT id, description, amount, status, created_at
                FROM journal_drafts
                WHERE tenant_id = %s
                  AND ABS(amount - %s) < 0.01
                  AND created_at >= NOW() - INTERVAL '30 days'
                ORDER BY created_at DESC
                LIMIT 1
            """, (tenant_id, amount))
            duplicate = cur.fetchone()

            if duplicate:
                return {
                    "ok": False,
                    "duplicate": True,
                    "draft_id": duplicate["id"],
                    "message": "⚠️ ეს ინვოისი უკვე დამუშავებულია!",
                    "existing_draft": {
                        "id": duplicate["id"],
                        "description": duplicate["description"],
                        "amount": float(duplicate["amount"]),
                        "status": duplicate["status"],
                        "created_at": str(duplicate["created_at"]),
                    },
                    "action_required": "confirm_reprocess",
                    "hint": "გამოიყენე force=true ხელახლა დასამუშავებლად",
                }

        # Try inserting with journal_entries column first, fallback without
        try:
            cur.execute("""
                INSERT INTO journal_drafts (
                    date, description, partner, amount,
                    debit_account, credit_account, account_code,
                    reason, confidence, status,
                    source_type, tenant_id, journal_entries, created_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, NOW()
                ) RETURNING id
            """, (
                date, description, partner, amount,
                debit_account, credit_account, debit_account,
                "invoice_ocr", 0.85, "pending_approval",
                source_type, tenant_id, journal_entries,
            ))
        except Exception:
            conn.rollback()
            cur.execute("""
                INSERT INTO journal_drafts (
                    date, description, partner, amount,
                    debit_account, credit_account, account_code,
                    reason, confidence, status,
                    source_type, tenant_id, created_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, NOW()
                ) RETURNING id
            """, (
                date, description, partner, amount,
                debit_account, credit_account, debit_account,
                "invoice_ocr", 0.85, "pending_approval",
                source_type, tenant_id,
            ))

        draft_id = cur.fetchone()["id"]
        conn.commit()

        return {
            "ok": True,
            "draft_id": draft_id,
            "date": date,
            "description": description,
            "partner": partner,
            "amount": amount,
            "net_amount": round(float(net_amount), 2),
            "vat_amount": round(float(vat_amount), 2) if vat_amount else None,
            "debit_account": debit_account,
            "credit_account": credit_account,
            "journal_entries": json.loads(journal_entries) if journal_entries else None,
            "confidence": 0.85,
            "status": "pending_approval",
            "tenant_id": tenant_id,
            "forced": force,
        }
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close()
        conn.close()


async def create_draft_from_invoice_async(
    invoice_fields: dict,
    tenant_id: str = "default",
    source_type: str = "invoice_ocr",
    force: bool = False,
) -> dict:
    """Async asyncpg version of create_draft_from_invoice for use in async route handlers."""
    from app.api.db import get_conn, _q

    amount = invoice_fields.get("amount")
    if not amount:
        return {"ok": False, "error": "თანხა ვერ ამოიღო ინვოისიდან"}

    partner = invoice_fields.get("partner") or ""
    date = invoice_fields.get("date") or datetime.now().strftime("%Y-%m-%d")
    vat_amount = invoice_fields.get("vat_amount")
    net_amount = invoice_fields.get("net_amount") or amount

    _inv_num = invoice_fields.get("invoice_number")
    _inv_num = str(_inv_num) if (_inv_num and str(_inv_num).lower() not in ("none", "null", "")) else None
    _partner = partner.strip() if partner and partner.lower() not in ("none", "null") else None

    if _inv_num and _partner:
        description = f"Invoice {_inv_num} — {_partner}"
    elif _partner:
        description = f"Invoice — {_partner}"
    elif _inv_num:
        description = f"Invoice #{_inv_num}"
    else:
        description = "Invoice (OCR)"

    from app.policy.localization.georgia_pack import get_account
    _combined = description.lower() + " " + (partner or "").lower()
    if any(k in _combined for k in ["communal", "კომუნალ", "electricity", "water", "gas", "გაზი", "elektro"]):
        debit_account = "7210"
    elif any(k in _combined for k in ["payroll", "salary", "ხელფასი", "wages"]):
        debit_account = "6100"
    elif any(k in _combined for k in ["rent", "იჯარა", "lease", "ქირა"]):
        debit_account = "7220"
    elif any(k in _combined for k in ["transport", "delivery", "მიტანა", "courier", "logistics"]):
        debit_account = "7130"
    else:
        debit_account = get_account("cost_of_service") or "7110"
    credit_account = get_account("accounts_payable") or "3310"

    journal_entries = None
    if vat_amount and vat_amount > 0 and net_amount and net_amount > 0:
        journal_entries = json.dumps([
            {"line": 1, "debit_account": debit_account, "credit_account": None,
             "amount": round(float(net_amount), 2), "description": f"Net expense — {description}"},
            {"line": 2, "debit_account": "1430", "credit_account": None,
             "amount": round(float(vat_amount), 2), "description": "Input VAT (დღგ)"},
            {"line": 3, "debit_account": None, "credit_account": credit_account,
             "amount": round(float(amount), 2), "description": "Accounts payable — total"},
        ])

    try:
        async with get_conn() as conn:
            if not force:
                dup = await conn.fetchrow(_q("""
                    SELECT id, description, amount, status, created_at
                    FROM journal_drafts
                    WHERE tenant_id = %s AND ABS(amount - %s) < 0.01
                      AND created_at >= NOW() - INTERVAL '30 days'
                    ORDER BY created_at DESC LIMIT 1
                """), tenant_id, amount)
                if dup:
                    return {
                        "ok": False, "duplicate": True, "draft_id": dup["id"],
                        "message": "⚠️ ეს ინვოისი უკვე დამუშავებულია!",
                        "existing_draft": {
                            "id": dup["id"], "description": dup["description"],
                            "amount": float(dup["amount"]), "status": dup["status"],
                            "created_at": str(dup["created_at"]),
                        },
                        "action_required": "confirm_reprocess",
                        "hint": "გამოიყენე force=true ხელახლა დასამუშავებლად",
                    }

            try:
                draft_id = await conn.fetchval(_q("""
                    INSERT INTO journal_drafts (
                        date, description, partner, amount,
                        debit_account, credit_account, account_code,
                        reason, confidence, status,
                        source_type, tenant_id, journal_entries, created_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    RETURNING id
                """),
                    date, description, partner, amount,
                    debit_account, credit_account, debit_account,
                    "invoice_ocr", 0.85, "pending_approval",
                    source_type, tenant_id, journal_entries,
                )
            except Exception:
                draft_id = await conn.fetchval(_q("""
                    INSERT INTO journal_drafts (
                        date, description, partner, amount,
                        debit_account, credit_account, account_code,
                        reason, confidence, status,
                        source_type, tenant_id, created_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    RETURNING id
                """),
                    date, description, partner, amount,
                    debit_account, credit_account, debit_account,
                    "invoice_ocr", 0.85, "pending_approval",
                    source_type, tenant_id,
                )

        return {
            "ok": True, "draft_id": draft_id,
            "date": date, "description": description, "partner": partner,
            "amount": amount, "net_amount": round(float(net_amount), 2),
            "vat_amount": round(float(vat_amount), 2) if vat_amount else None,
            "debit_account": debit_account, "credit_account": credit_account,
            "journal_entries": json.loads(journal_entries) if journal_entries else None,
            "confidence": 0.85, "status": "pending_approval",
            "tenant_id": tenant_id, "forced": force,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _parse_date(date_str: str) -> Optional[str]:
    formats = [
        "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d",
        "%d,%m,%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return date_str


def _extract_invoice_number(ids: list) -> Optional[str]:
    if not ids:
        return None
    for id_val in ids:
        if len(str(id_val)) < 9:
            return str(id_val)
    return str(ids[0]) if ids else None


def extract_text(file_path: str) -> str:
    """მარტივი ტექსტის ამოღება (fallback)"""
    try:
        import fitz
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return ""
