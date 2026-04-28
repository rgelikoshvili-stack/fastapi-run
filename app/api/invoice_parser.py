import io
import re
from typing import Optional

from app.api.invoice_ocr_fallback import extract_text_with_ocr


def _clean_amount(value: str) -> Optional[float]:
    if not value:
        return None

    v = value.strip()
    v = v.replace("\u00a0", " ")
    v = re.sub(r"[^\d,.\-]", "", v)

    if not v:
        return None

    if "," in v and "." in v:
        if v.rfind(",") > v.rfind("."):
            v = v.replace(".", "")
            v = v.replace(",", ".")
        else:
            v = v.replace(",", "")
    elif "," in v:
        parts = v.split(",")
        if len(parts[-1]) == 2:
            v = v.replace(",", ".")
        else:
            v = v.replace(",", "")

    try:
        return float(v)
    except Exception:
        return None


def _first_date(text: str) -> Optional[str]:
    patterns = [
        r"\b\d{2}[./-]\d{2}[./-]\d{4}\b",
        r"\b\d{4}[./-]\d{2}[./-]\d{2}\b",
        r"\b\d{2}[./-]\d{2}[./-]\d{2}\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(0)
    return None


def _extract_invoice_number(text: str) -> Optional[str]:
    patterns = [
        r"(?:invoice\s*(?:no|number|n)?|inv\.?\s*(?:no|number|n)?|ანგარიშფაქტურა\s*(?:N|№|#)?|ინვოისი\s*(?:N|№|#)?)\s*[:#№\-]?\s*([A-Z0-9][A-Z0-9/\-._]*)",
        r"\b(?:N|№)\s*([A-Z0-9][A-Z0-9/\-._]{2,})\b",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = m.group(1).strip(" .,:;")
            if len(value) >= 3:
                return value
    return None


def _extract_partner(text: str) -> Optional[str]:
    patterns = [
        r"\b(შპს\s+[^\n,]{2,80})",
        r"\b(სს\s+[^\n,]{2,80})",
        r"\b(LLC\s+[^\n,]{2,80})",
        r"\b(Ltd\.?\s+[^\n,]{2,80})",
        r"\b(Inc\.?\s+[^\n,]{2,80})",
        r"\b(GmbH\s+[^\n,]{2,80})",
        r"\b(ООО\s+[^\n,]{2,80})",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    alte = re.search(r"(სს\s*ალტე\s*ბანკი)", text, re.IGNORECASE)
    if alte:
        return alte.group(1).strip()

    return None


def _extract_currency(text: str) -> str:
    lower = text.lower()

    if re.search(r"\busd\b|\$", lower):
        return "USD"
    if re.search(r"\beur\b|€", lower):
        return "EUR"
    if re.search(r"\bgel\b|ლარი", lower):
        return "GEL"

    return "GEL"


def _extract_labeled_amount(text: str, labels: list[str]) -> Optional[float]:
    joined = "|".join(labels)
    patterns = [
        rf"(?:{joined})\s*[:\-]?\s*([0-9][0-9\s,\.]*)",
        rf"(?:{joined})[^\n]{{0,25}}?([0-9][0-9\s,\.]*)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            amount = _clean_amount(m.group(1))
            if amount is not None:
                return amount
    return None


def _extract_all_amounts(text: str) -> list[float]:
    matches = re.findall(
        r"(?<!\d)(\d{1,3}(?:[ ,]\d{3})*(?:[.,]\d{2})|\d+(?:[.,]\d{2}))(?!\d)",
        text,
    )
    amounts = []
    for raw in matches:
        value = _clean_amount(raw)
        if value is not None:
            amounts.append(value)
    return amounts


def _guess_total_amount(text: str) -> Optional[float]:
    total = _extract_labeled_amount(
        text,
        ["total", "amount due", "grand total", "სულ", "ჯამი", "გადასახდელი"],
    )
    if total is not None:
        return total

    amounts = [a for a in _extract_all_amounts(text) if a > 0]
    if not amounts:
        return None

    return max(amounts)


def _guess_vat_amount(text: str, total_amount: Optional[float]) -> Optional[float]:
    vat = _extract_labeled_amount(
        text,
        ["vat", "დღგ", "ндс"],
    )
    if vat is not None:
        return vat

    percent_match = re.search(r"(18\s*%)", text)
    if percent_match and total_amount:
        guessed = round(total_amount * 18 / 118, 2)
        if guessed > 0:
            return guessed

    return None


def _extract_pdf_text(content: bytes) -> str:
    try:
        import fitz
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(doc[i].get_text() for i in range(len(doc)))
    except Exception:
        return ""


def parse_invoice_pdf(content: bytes) -> dict:
    result = {
        "invoice_number": None,
        "invoice_date": None,
        "partner": None,
        "total_amount": None,
        "vat_amount": None,
        "currency": "GEL",
        "items": [],
        "raw_text": "",
        "ocr_used": False,
        "extraction_confidence": 0.0,
        "review_required": True,
    }

    text = _extract_pdf_text(content)

    # OCR fallback თუ ტექსტი ვერ ამოიკითხა ან ძალიან მოკლეა
    if not text or len(text.strip()) < 20:
        ocr_text = extract_text_with_ocr(content)
        if ocr_text:
            text = ocr_text
            result["ocr_used"] = True

    result["raw_text"] = text[:4000]

    normalized_text = text.replace("\u00a0", " ")
    normalized_text = re.sub(r"[ \t]+", " ", normalized_text)

    result["invoice_number"] = _extract_invoice_number(normalized_text)
    result["invoice_date"] = _first_date(normalized_text)
    result["partner"] = _extract_partner(normalized_text)
    result["currency"] = _extract_currency(normalized_text)

    total_amount = _guess_total_amount(normalized_text)
    vat_amount = _guess_vat_amount(normalized_text, total_amount)

    # VAT sanity check
    if vat_amount and total_amount and vat_amount > total_amount:
        vat_amount = None

    result["total_amount"] = total_amount
    result["vat_amount"] = vat_amount

    # Field completeness score
    fields = [
        result["invoice_number"],
        result["invoice_date"],
        result["partner"],
        result["total_amount"],
    ]

    filled = sum(1 for f in fields if f not in (None, "", 0))
    score = filled / len(fields)
    result["extraction_confidence"] = round(score, 2)

    # Review flag
    result["review_required"] = result["extraction_confidence"] < 0.5

    return result