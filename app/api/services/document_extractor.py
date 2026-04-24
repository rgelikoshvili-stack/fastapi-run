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
    "payg": "3380",
    "bank fee": "7190",
    "commission": "7190",
    "საკომ": "7190",
    "salary": "7120",
    "ხელფასი": "7120",
    "payroll": "7120",
    "office": "7180",
    "revenue": "6100",
    "income": "6100",
    "vat receivable": "1760",
    "vat payable": "3310",
    "rent": "7310",
    "transport": "7730",
    "advertising": "7710",
    "entertainment": "7720",
    "cit": "3340",
    "pit": "3320",
    "dividend": "3370",
    "დივიდენდი": "3370",
    "tax": "3380",
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


class ExtractedLineItem(BaseModel):
    description: str
    unit: Optional[str] = None
    quantity: Optional[float] = None
    amount_with_vat: Optional[float] = None
    vat_amount: Optional[float] = 0
    excise: Optional[float] = 0


class ExtractedDocument(BaseModel):
    document_type: Literal[
        "tax_invoice", "waybill", "contract",
        "receipt", "bank_statement", "unknown"
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


EXTRACTION_PROMPT = """You are Bridge Hub's document intelligence system for Georgian accounting.
Extract structured data from the document text below.

Rules:
1. INN/ID numbers: 9 digits (legal entity) or 11 digits (individual/entrepreneur)
2. Numbers as decimal (123.45), not string
3. Dates in YYYY-MM-DD format
4. Use null for missing fields
5. Preserve original text for names

Document types:
- tax_invoice: Georgian tax invoice (სასაქონლო ზედნადები)
- waybill: delivery document (სასაქონლო ნაშთი)
- contract: agreement (ხელშეკრულება)
- receipt: payment receipt
- bank_statement: bank statement

Return ONLY valid JSON, no explanation.

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
        return ExtractedDocument(**data)
    except json.JSONDecodeError as e:
        log.error("LLM JSON parse failed: %s", e)
        return _regex_extract(text)
    except Exception as e:
        log.error("LLM extraction failed: %s", e)
        return _regex_extract(text)


def _regex_extract(text: str) -> ExtractedDocument:
    """Best-effort regex fallback when LLM not available."""
    import re

    inn_pattern = re.compile(r'\b(\d{9}|\d{11})\b')
    amount_pattern = re.compile(r'(\d{1,10}[.,]\d{2})')
    date_pattern = re.compile(r'(\d{2}[./]\d{2}[./]\d{4}|\d{4}-\d{2}-\d{2})')

    inns = inn_pattern.findall(text)
    amounts = amount_pattern.findall(text)
    dates = date_pattern.findall(text)

    seller_inn = inns[0] if len(inns) > 0 else None
    buyer_inn = inns[1] if len(inns) > 1 else None

    total = None
    if amounts:
        try:
            total = float(amounts[-1].replace(",", "."))
        except Exception:
            pass

    issue_date = None
    if dates:
        d = dates[0]
        try:
            if "-" in d:
                issue_date = d
            else:
                parts = re.split(r'[./]', d)
                issue_date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        except Exception:
            pass

    doc_type = "unknown"
    text_lower = text.lower()
    if any(kw in text_lower for kw in ["ზედნადები", "invoice", "ინვოისი"]):
        doc_type = "tax_invoice"
    elif any(kw in text_lower for kw in ["ხელშეკრულება", "contract", "agreement"]):
        doc_type = "contract"
    elif any(kw in text_lower for kw in ["ამონაწერი", "statement", "ბანკი"]):
        doc_type = "bank_statement"

    from app.api.services.journal_service import validate_georgian_inn
    validated_seller = seller_inn if seller_inn and validate_georgian_inn(seller_inn) else None
    validated_buyer = buyer_inn if buyer_inn and validate_georgian_inn(buyer_inn) else None

    return ExtractedDocument(
        document_type=doc_type,
        issue_date=issue_date,
        seller=ExtractedParty(inn=validated_seller),
        buyer=ExtractedParty(inn=validated_buyer),
        total_with_vat=total,
        notes=text[:500],  # classifier searches notes for keywords
    )
