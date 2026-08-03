"""app/api/services/document_extractor.py
LLM-based structured data extraction from document text.
"""
import json
import logging
import os
from typing import Optional, Literal
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

DEFAULT_ACCOUNT_MAPPING = {
    "payg": "3330",        # დასაქ.საპ. (was 3380 — missing)
    "bank fee": "7510",    # სბ.სკ. (was 7190 — missing)
    "commission": "7510",  # სბ.სკ.
    "საკომ": "7510",       # სბ.სკ.
    "salary": "7210",      # ხ.ხ.
    "ხელფასი": "7210",
    "payroll": "7210",
    "office": "7810",      # სხ.ა.ხ. (was 7180 — missing)
    "revenue": "6110",     # გ-ვ.შემ. (was 6100 — missing)
    "income": "6110",      # გ-ვ.შემ.
    "vat receivable": "3311",  # ჩათვ.დღგ (was 1760 — missing)
    "vat payable": "3310",     # დღგ გად.
    "rent": "7310",        # ქ.ხ.
    "transport": "7730",   # სატ.ხ.
    "advertising": "7710", # რ.ხ.
    "entertainment": "7720",  # წ.ხ.
    "cit": "3340",         # CIT/მოგ.
    "pit": "3320",         # PIT/საშ.
    "dividend": "3370",    # გად.დივ.
    "დივიდენდი": "3370",
    "tax": "3320",         # PIT (was 3380 — missing; default to PIT)
}

_INVALID_CODES = {"", "-", "ETC", "etc", "N/A", "n/a", "None", "null", "undefined"}


def resolve_account_code(code: Optional[str], description: str = "") -> Optional[str]:
    """Return a valid COA code, falling back to keyword mapping for invalid/missing codes."""
    if code and code not in _INVALID_CODES:
        return code
    desc_lower = (description or "").lower()
    for keyword, account in DEFAULT_ACCOUNT_MAPPING.items():
        if keyword.lower() in desc_lower:
            return account
    return None


class ExtractedParty(BaseModel):
    inn: Optional[str] = None
    name: Optional[str] = None
    bank_name: Optional[str] = None
    bank_account: Optional[str] = None
    swift: Optional[str] = None


class ExtractedLineItem(BaseModel):
    description: str
    unit: Optional[str] = None
    quantity: Optional[float] = None
    amount_with_vat: Optional[float] = None
    vat_amount: Optional[float] = 0
    excise: Optional[float] = 0


class ExtractedDocument(BaseModel):
    document_type: Literal[
        "tax_invoice", "waybill", "invoice", "contract",
        "act", "delivery", "receipt", "bank_statement", "unknown"
    ] = "unknown"
    document_series: Optional[str] = None
    document_number: Optional[str] = None
    issue_date: Optional[str] = None
    operation_period: Optional[str] = None

    seller: ExtractedParty = Field(default_factory=ExtractedParty)
    buyer: ExtractedParty = Field(default_factory=ExtractedParty)

    line_items: list[ExtractedLineItem] = []

    total_with_vat: Optional[float] = None
    total_vat: Optional[float] = None
    net_amount: Optional[float] = None

    currency: str = "GEL"
    notes: Optional[str] = None

    # Extended fields for triangle matching
    waybill_number: Optional[str] = None        # waybill doc number
    waybill_date: Optional[str] = None          # waybill issue date
    invoice_number: Optional[str] = None        # commercial invoice number
    invoice_date: Optional[str] = None          # commercial invoice date
    related_waybill_number: Optional[str] = None  # tax_invoice → references waybill
    contract_number: Optional[str] = None       # referenced contract
    delivery_date: Optional[str] = None         # delivery confirmation date
    act_number: Optional[str] = None            # act of completion number
    total_amount: Optional[float] = None        # alias for triangle matching
    seller_inn: Optional[str] = None            # flat alias for triangle
    buyer_inn: Optional[str] = None             # flat alias for triangle
    provider_type: Optional[str] = None         # fp/im/shps/sp/npo/unknown


EXTRACTION_PROMPT = """You are Bridge Hub's document intelligence system for Georgian accounting.
Extract structured data from the document text below.

Rules:
1. INN/ID numbers: 9 digits (legal entity) or 11 digits (individual/entrepreneur)
2. Numbers as decimal (123.45), not string
3. Dates in YYYY-MM-DD format
4. Use null for missing fields
5. Preserve original text for names

CRITICAL — seller vs buyer identification:
- Georgian "გამყიდველი" = SELLER (the company issuing/sending the invoice)
- Georgian "მყიდველი" = BUYER (the company receiving and paying the invoice)
- The seller INN often appears in the bank payment details section ("რეკვიზიტები")
- The buyer INN often appears in the billing/delivery section under "მყიდველი"
- Do NOT swap seller and buyer — the company that ISSUED the document is the seller

Document types:
- tax_invoice: Georgian tax invoice (ანგარიშ-ფაქტურა / სასაქონლო ზედნადები with VAT)
- waybill: delivery / consignment note (სასაქონლო ზედნადები, ტვირთის გადაზიდვის ფურცელი)
- invoice: commercial invoice for goods/services (ინვოისი / კომერციული ანგარიში)
- contract: service or supply agreement (ხელშეკრულება / შეთანხმება)
- act: act of completion / acceptance (მიღება-ჩაბარების აქტი)
- delivery: delivery confirmation (მიწოდების დამადასტურებელი)
- receipt: payment receipt (ქვითარი / ჩეკი)
- bank_statement: bank statement (ამონაწერი)

Extra fields to extract (use null if absent):
- waybill_number, waybill_date: for waybill documents
- invoice_number, invoice_date: for invoice documents
- related_waybill_number: reference to waybill in tax_invoice
- contract_number: referenced contract number
- act_number: act/completion number
- delivery_date: for delivery documents

Bank/payment details (from the "რეკვიზიტები" / payment details section):
- seller.bank_name: seller's bank name (e.g. "სს საქართველოს ბანკი")
- seller.bank_account: seller's IBAN / account number (e.g. "GE44BG0000000352876900")
- seller.swift: seller's SWIFT/BIC code (e.g. "BAGAGE22")
- buyer.bank_name, buyer.bank_account, buyer.swift: same for buyer if present

Return ONLY valid JSON matching the ExtractedDocument schema, no explanation.

Document text:
---
{document_text}
---

JSON:"""


async def extract_document(text: str, llm_service=None) -> ExtractedDocument:
    """Extract structured data from document text using LLM or fallback regex."""
    if not text or len(text) < 50:
        return ExtractedDocument(document_type="unknown", notes="Text too short")

    if llm_service:
        return await _llm_extract(text, llm_service)

    return _regex_extract(text)


def _populate_flat_aliases(doc: "ExtractedDocument") -> None:
    """Populate flat seller_inn / buyer_inn / total_amount from nested fields."""
    if not doc.seller_inn and doc.seller:
        doc.seller_inn = doc.seller.inn
    if not doc.buyer_inn and doc.buyer:
        doc.buyer_inn = doc.buyer.inn
    if doc.total_amount is None:
        doc.total_amount = doc.total_with_vat
    if not doc.provider_type and doc.seller_inn:
        from app.api.services.contract_classifier import classify_provider_type
        doc.provider_type = classify_provider_type(
            doc.seller.name if doc.seller else None,
            doc.seller_inn
        ).value


async def _llm_extract(text: str, llm_service) -> ExtractedDocument:
    truncated = text[:8000]
    try:
        prompt = EXTRACTION_PROMPT.format(document_text=truncated)
        response = await llm_service.complete(
            prompt=prompt,
            model="gpt-4o",
            temperature=0.1,
            max_tokens=2000,
        )
        raw = response.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        doc = ExtractedDocument(**data)
        _populate_flat_aliases(doc)
        return doc
    except json.JSONDecodeError as e:
        log.error("LLM JSON parse failed: %s", e)
        return _regex_extract(text)
    except Exception as e:
        log.error("LLM extraction failed: %s", e)
        return _regex_extract(text)


def _extract_inn_near(text: str, keywords: list[str], window: int = 400) -> str | None:
    """Return first valid INN found within `window` chars after any of the keywords.
    Uses whole-word matching for Georgian keywords: keyword must not be preceded
    by a Georgian letter (prevents 'მყიდველი' matching inside 'გამყიდველი').
    """
    import re
    inn_pat = re.compile(r'\b(\d{9}|\d{11})\b')
    # Negative lookbehind for Georgian letters (U+10D0–U+10FF)
    _geo_lb = r'(?<![ა-ჰა-ჿ])'
    for kw in keywords:
        pattern = re.compile(_geo_lb + re.escape(kw.lower()), re.IGNORECASE)
        m = pattern.search(text.lower())
        if m:
            section = text[m.start(): m.start() + window]
            inn_m = inn_pat.search(section)
            if inn_m:
                return inn_m.group(1)
    return None


def _extract_tax_invoice_inns(text: str) -> tuple[str | None, str | None, str | None, float | None, str | None]:
    """
    Georgian tax invoice field-number extraction.
    Returns (seller_inn, buyer_inn, series_number, total_vat, linked_waybill).
    Fields: 5.1 = seller INN, 6.1 = buyer INN.
    """
    import re

    # seller INN — field 5.1
    seller_inn = None
    for pat in [
        r'5[\.\s]*1[\s\S]{0,30}?(\d{9})',
        r'გამყიდველ[\s\S]{0,50}?(\d{9})',
        r'საიდენტიფ[^\n]{0,30}(\d{9})[^\n]{0,30}5[\.\s]*[12]',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            seller_inn = m.group(1)
            break

    # buyer INN — field 6.1
    buyer_inn = None
    for pat in [
        r'6[\.\s]*1[\s\S]{0,30}?(\d{9})',
        r'მყიდველ[\s\S]{0,50}?(\d{9})',
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            cand = m.group(1)
            if cand != seller_inn:
                buyer_inn = cand
                break

    # series number (e.g. ეა-85 4878150)
    series_number = None
    m = re.search(r'(ეა[-\s]*\d{2}[\s\-]\d{7,8})', text)
    if m:
        series_number = m.group(1)

    # total VAT — "სულ დასარიცხი X.XX"
    total_vat = None
    m = re.search(r'სულ\s+დასარიცხ[^\d]*(\d+[\.,]\d{2})', text)
    if m:
        try:
            total_vat = float(m.group(1).replace(",", "."))
        except Exception as e:
            log.warning("unexpected error: %s", e)

    # linked waybill number (10–11 digit starting with 0)
    linked_waybill = None
    m = re.search(r'\b(0\d{9,10})\b', text)
    if m:
        linked_waybill = m.group(1)

    return seller_inn, buyer_inn, series_number, total_vat, linked_waybill


def _regex_extract(text: str) -> ExtractedDocument:
    """Best-effort regex fallback when LLM not available."""
    import re

    inn_pattern = re.compile(r'\b(\d{9}|\d{11})\b')
    amount_pattern = re.compile(r'(\d{1,10}[.,]\d{2})')
    date_pattern = re.compile(r'(\d{2}[./]\d{2}[./]\d{4}|\d{4}-\d{2}-\d{2})')

    amounts = amount_pattern.findall(text)
    dates = date_pattern.findall(text)

    # Keyword-anchored party extraction (Georgian + English)
    seller_inn = _extract_inn_near(text, ["გამყიდველი", "seller", "vendor", "რეკვიზიტები"])
    buyer_inn  = _extract_inn_near(text, ["მყიდველი", "buyer", "customer", "purchaser", "recipient"])

    # Fallback: first two INNs in document order, but avoid duplicates
    if not seller_inn or not buyer_inn:
        all_inns = inn_pattern.findall(text)
        # De-duplicate preserving order
        seen, unique_inns = set(), []
        for i in all_inns:
            if i not in seen:
                seen.add(i); unique_inns.append(i)
        if not seller_inn and not buyer_inn:
            seller_inn = unique_inns[0] if len(unique_inns) > 0 else None
            buyer_inn  = unique_inns[1] if len(unique_inns) > 1 else None
        elif not seller_inn:
            # buyer found — take first INN that isn't buyer as seller
            for i in unique_inns:
                if i != buyer_inn:
                    seller_inn = i; break
        elif not buyer_inn:
            for i in unique_inns:
                if i != seller_inn:
                    buyer_inn = i; break

    total = None
    if amounts:
        try:
            total = float(amounts[-1].replace(",", "."))
        except Exception as e:
            log.warning("unexpected error: %s", e)

    issue_date = None
    if dates:
        d = dates[0]
        try:
            if "-" in d:
                issue_date = d
            else:
                parts = re.split(r'[./]', d)
                issue_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        except Exception as e:
            log.warning("unexpected error: %s", e)

    doc_type = "unknown"
    text_lower = text.lower()

    # Detect tax_invoice early so we can apply field-number extraction
    if any(kw in text_lower for kw in ["ანგარიშ-ფაქტურა", "tax invoice"]):
        doc_type = "tax_invoice"
        ti_seller, ti_buyer, ti_series, ti_vat, ti_waybill = _extract_tax_invoice_inns(text)
        if ti_seller:
            seller_inn = ti_seller
        if ti_buyer:
            buyer_inn = ti_buyer

    # More specific matching — order matters (most specific first)
    if any(kw in text_lower for kw in ["ანგარიშ-ფაქტურა", "tax invoice"]):
        doc_type = "tax_invoice"
    elif any(kw in text_lower for kw in ["მიღება-ჩაბარებ", "acceptance act", "completion act", "act of"]):
        doc_type = "act"
    elif any(kw in text_lower for kw in ["სასაქონლო ზედნადები", "waybill", "ზედნადები"]):
        doc_type = "waybill"
    elif any(kw in text_lower for kw in ["ხელშეკრულება", "contract", "agreement", "შეთანხმება"]):
        doc_type = "contract"
    elif any(kw in text_lower for kw in ["ინვოისი", "invoice", "commercial invoice"]):
        doc_type = "invoice"
    elif any(kw in text_lower for kw in ["მიწოდება", "delivery note", "dispatch"]):
        doc_type = "delivery"
    elif any(kw in text_lower for kw in ["ამონაწერი", "statement", "bank statement"]):
        doc_type = "bank_statement"
    elif any(kw in text_lower for kw in ["ქვითარი", "receipt", "ჩეკი"]):
        doc_type = "receipt"

    # Extract doc numbers via common patterns
    doc_number = None
    num_match = re.search(r'(?:№|#|N|No\.?)\s*([A-Za-z0-9\-/]+)', text)
    if num_match:
        doc_number = num_match.group(1)

    # Waybill-specific number
    waybill_number = None
    wb_match = re.search(r'(?:ზედნადები|waybill)[^\d]*(\d{5,12})', text, re.IGNORECASE)
    if wb_match:
        waybill_number = wb_match.group(1)

    # Related waybill reference in tax_invoice
    related_wb = None
    ref_match = re.search(r'(?:ზედნადები|waybill)\s*(?:№|#|N)?\s*(\d{5,12})', text, re.IGNORECASE)
    if ref_match and doc_type == "tax_invoice":
        related_wb = ref_match.group(1)

    from app.api.services.journal_service import validate_georgian_inn
    validated_seller = seller_inn if seller_inn and validate_georgian_inn(seller_inn) else None
    validated_buyer = buyer_inn if buyer_inn and validate_georgian_inn(buyer_inn) else None

    # Try to extract VAT from amounts — last large amount usually total, second-to-last is net
    vat_total: float | None = None
    net_amount: float | None = None
    if len(amounts) >= 2:
        try:
            vat_total = float(amounts[-1].replace(",", "."))
            net_amount = float(amounts[-2].replace(",", "."))
        except Exception as e:
            log.warning("unexpected error: %s", e)

    # Classify provider type from INNs
    from app.api.services.contract_classifier import classify_provider_type
    p_type = classify_provider_type(None, validated_seller)

    # For tax invoices, prefer field-number extracted values
    _ti_series = None
    _ti_vat = None
    _ti_waybill = None
    if doc_type == "tax_invoice":
        _, _, _ti_series, _ti_vat, _ti_waybill = _extract_tax_invoice_inns(text)

    return ExtractedDocument(
        document_type=doc_type,
        document_number=_ti_series or doc_number,
        issue_date=issue_date,
        seller=ExtractedParty(inn=validated_seller),
        buyer=ExtractedParty(inn=validated_buyer),
        total_with_vat=_ti_vat or total,
        net_amount=net_amount,
        notes=text[:500],
        # flat aliases
        waybill_number=waybill_number if doc_type == "waybill" else None,
        waybill_date=issue_date if doc_type == "waybill" else None,
        invoice_number=_ti_series or (doc_number if doc_type in ("invoice", "tax_invoice") else None),
        invoice_date=issue_date if doc_type in ("invoice", "tax_invoice") else None,
        related_waybill_number=_ti_waybill or related_wb,
        total_amount=_ti_vat or total,
        seller_inn=validated_seller,
        buyer_inn=validated_buyer,
        provider_type=p_type.value,
    )
