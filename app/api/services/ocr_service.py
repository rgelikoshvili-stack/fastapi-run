"""
app/api/services/ocr_service.py
Bridge Hub — Invoice OCR Service
Duplicate detection + doc_analyzer.py
"""
import re
from datetime import datetime
from typing import Optional
from app.api.doc_analyzer import analyze, to_dict


def extract_invoice_fields(filename: str, data: bytes) -> dict:
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
    if amount:
        vat_amount = round(amount * 0.18 / 1.18, 2)

    return {
        "ok": True,
        "filename": filename,
        "doc_format": fields.get("doc_format"),
        "ocr_used": fields.get("ocr_used", False),
        "invoice_number": invoice_number,
        "date": date,
        "amount": amount,
        "currency": currency,
        "vat_amount": vat_amount,
        "net_amount": round(amount - vat_amount, 2) if amount and vat_amount else amount,
        "partner": partner,
        "iban": iban,
        "warnings": fields.get("warnings", []),
        "raw_amounts": amounts[:5],
        "raw_dates": dates[:5],
    }


def create_draft_from_invoice(
    invoice_fields: dict,
    tenant_id: str = "default",
    source_type: str = "invoice_ocr",
    force: bool = False,
) -> dict:
    """
    OCR შედეგიდან journal draft-ის შექმნა.
    force=True — duplicate-ის შემთხვევაშიც ქმნის ახალ draft-ს.
    """
    from app.api.db import get_db
    import psycopg2.extras

    amount = invoice_fields.get("amount")
    if not amount:
        return {"ok": False, "error": "თანხა ვერ ამოიღო ინვოისიდან"}

    partner = invoice_fields.get("partner") or ""
    date = invoice_fields.get("date") or datetime.now().strftime("%Y-%m-%d")

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
    debit_account = get_account("cost_of_service")
    credit_account = get_account("bank")

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
            "invoice_ocr", 0.75, "pending_approval",
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
            "debit_account": debit_account,
            "credit_account": credit_account,
            "confidence": 0.75,
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
    """
    მარტივი ტექსტის ამოღება (fallback)
    """
    try:
        import fitz  # PyMuPDF
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