"""
app/ai_systems/document_ai.py
Bridge Hub — Document AI (Phase 5)

Pipeline:
  File → OCR (doc_analyzer) → LLM extraction → Business Logic AI → journal draft

Wraps existing services — no duplication:
  - ocr_service.py      (extract_invoice_fields)
  - document_extractor.py (ExtractedDocument, resolve_account_code)
  - business_logic_ai.py  (generate_journal_entries)
  - posting_service.py    (create_journal_draft)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

log = logging.getLogger(__name__)

# Re-use existing services
from app.api.services.ocr_service import extract_invoice_fields
from app.api.services.document_extractor import (
    ExtractedDocument,
    resolve_account_code,
    extract_document,
)
from app.ai_systems.business_logic_ai import generate_journal_entries


# ─────────────────────────────────────────────────────────────
# Document type → transaction_type mapping
# ─────────────────────────────────────────────────────────────
_DOC_TYPE_MAP = {
    "tax_invoice": "vat_purchase",
    "waybill":     "vat_purchase",
    "receipt":     "expense",
    "contract":    "expense",
    "bank_statement": "bank_fee",
}


# ─────────────────────────────────────────────────────────────
# Main pipeline function
# ─────────────────────────────────────────────────────────────

async def process_document_to_draft(
    filename: str,
    file_bytes: bytes,
    tenant_id: str = "default",
    llm_service=None,
) -> dict:
    """
    Full Document AI pipeline:
      1. OCR extraction (existing ocr_service.py)
      2. LLM structured extraction (existing document_extractor.py)
      3. Business Logic AI → journal lines
      4. Return ready-to-save draft dict

    Does NOT save to DB — caller decides (human gate may apply).
    """
    # Step 1 — OCR
    ocr_fields = extract_invoice_fields(filename, file_bytes)
    ocr_ok = ocr_fields.get("ok") and ocr_fields.get("amount")

    # Step 2 — LLM structured extraction
    extracted: Optional[ExtractedDocument] = None
    if ocr_fields.get("ocr_used") or (filename or "").lower().endswith(".pdf"):
        text_hint = _build_text_hint(ocr_fields)
        try:
            extracted = await extract_document(text_hint, llm_service)
        except Exception as e:
            log.warning("document_extractor failed: %s", e)

    # Step 3 — Determine amount, partner, type
    amount = float(ocr_fields.get("amount") or 0)
    partner = ocr_fields.get("partner") or (
        extracted.seller.name if extracted and extracted.seller else None
    ) or "Unknown"
    invoice_number = ocr_fields.get("invoice_number") or (
        extracted.document_number if extracted else None
    )
    doc_type = (extracted.document_type if extracted else "unknown") or "unknown"
    transaction_type = _DOC_TYPE_MAP.get(doc_type, "expense")

    description = _build_description(filename, partner, invoice_number, doc_type)

    # Step 4 — Business Logic AI generates journal lines
    journal_result = generate_journal_entries(
        description=description,
        amount=amount,
        transaction_type=transaction_type,
        context={
            "partner": partner,
            "invoice_number": invoice_number,
            "doc_type": doc_type,
            "vat_amount": ocr_fields.get("vat_amount"),
        },
        tenant_id=tenant_id,
    )

    # Step 5 — Determine COA codes from lines
    dr_account = None
    cr_account = None
    for ln in journal_result.get("lines", []):
        if ln["side"] == "dr" and not dr_account:
            dr_account = ln["account"]
        if ln["side"] == "cr" and not cr_account:
            cr_account = ln["account"]

    # Fallback COA resolution using document_extractor's keyword mapping
    if not dr_account:
        dr_account = resolve_account_code(None, description) or "7910"
    if not cr_account:
        cr_account = "1120"

    return {
        "ok": amount > 0,
        "description": description,
        "amount": amount,
        "currency": ocr_fields.get("currency", "GEL"),
        "partner": partner,
        "debit_account": dr_account,
        "credit_account": cr_account,
        "journal_lines": journal_result.get("lines", []),
        "confidence": journal_result.get("confidence", 0.7),
        "source": journal_result.get("source", "unknown"),
        "doc_type": doc_type,
        "invoice_number": invoice_number,
        "vat_amount": ocr_fields.get("vat_amount"),
        "net_amount": ocr_fields.get("net_amount"),
        "date": ocr_fields.get("date") or (extracted.issue_date if extracted else None),
        "seller_inn": extracted.seller.inn if extracted and extracted.seller else None,
        "buyer_inn": extracted.buyer.inn if extracted and extracted.buyer else None,
        "ocr_used": ocr_fields.get("ocr_used", False),
        "extraction_notes": journal_result.get("notes", ""),
    }


def enrich_draft_with_ai(draft: dict, tenant_id: str = "default") -> dict:
    """
    Enrich an existing draft dict with AI-generated journal lines.
    Useful when a draft was created without journal lines.
    """
    if draft.get("journal_lines"):
        return draft  # already has lines

    description = draft.get("description", "")
    amount = float(draft.get("amount") or 0)

    result = generate_journal_entries(
        description=description,
        amount=amount,
        context={
            "partner": draft.get("partner"),
        },
        tenant_id=tenant_id,
    )

    draft["journal_lines"] = result.get("lines", [])
    draft["confidence"] = result.get("confidence", 0.0)
    draft["ai_source"] = result.get("source", "unknown")
    return draft


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _build_text_hint(ocr_fields: dict) -> str:
    parts = []
    if ocr_fields.get("partner"):
        parts.append(f"Partner: {ocr_fields['partner']}")
    if ocr_fields.get("invoice_number"):
        parts.append(f"Invoice: {ocr_fields['invoice_number']}")
    if ocr_fields.get("amount"):
        parts.append(f"Amount: {ocr_fields['amount']} {ocr_fields.get('currency','GEL')}")
    if ocr_fields.get("date"):
        parts.append(f"Date: {ocr_fields['date']}")
    return "\n".join(parts) if parts else "document"


def _build_description(filename: str, partner: str, invoice_number: Optional[str], doc_type: str) -> str:
    base = filename.rsplit(".", 1)[0] if filename else "document"
    parts = [partner or base]
    if invoice_number:
        parts.append(f"#{invoice_number}")
    if doc_type and doc_type != "unknown":
        parts.append(doc_type.replace("_", " ").title())
    return " | ".join(parts)
