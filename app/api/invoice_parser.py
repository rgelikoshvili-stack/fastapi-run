import pdfplumber, re, io
from typing import Optional

def parse_invoice_pdf(content: bytes) -> dict:
    result = {
        "invoice_number": None,
        "invoice_date": None,
        "partner": None,
        "total_amount": None,
        "vat_amount": None,
        "currency": "GEL",
        "items": [],
        "raw_text": ""
    }

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        result["raw_text"] = text[:2000]

    lines = text.splitlines()

    for line in lines:
        l = line.strip()

        # invoice number
        if not result["invoice_number"]:
            m = re.search(r'(?:invoice|inv)[\s#:\-]+([A-Z0-9\-/]{3,})', l, re.IGNORECASE)
            if m: result["invoice_number"] = m.group(1)

        # date
        if not result["invoice_date"]:
            m = re.search(r'(\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}|\d{4}[./\-]\d{2}[./\-]\d{2})', l)
            if m: result["invoice_date"] = m.group(1)

        # partner/company
        if not result["partner"]:
            m = re.search(r'(შპს|სს|ООО|LLC|Ltd|Inc|GmbH)\s+([^\n,]{3,50})', l, re.IGNORECASE)
            if m: result["partner"] = m.group(0).strip()

        # total
        if not result["total_amount"]:
            m = re.search(r'(total|სულ|ჯამი|amount due)[:\s]+([0-9,\s]+\.?\d*)', l, re.IGNORECASE)
            if m:
                val = re.sub(r'[,\s]', '', m.group(2))
                try: result["total_amount"] = float(val)
                except: pass

        # vat
        if not result["vat_amount"]:
            m = re.search(r'(vat|დღგ|ндс)[:\s]+([0-9,\s]+\.?\d*)', l, re.IGNORECASE)
            if m:
                val = re.sub(r'[,\s]', '', m.group(2))
                try: result["vat_amount"] = float(val)
                except: pass

        # currency
        if "usd" in l.lower(): result["currency"] = "USD"
        elif "eur" in l.lower(): result["currency"] = "EUR"

    return result
