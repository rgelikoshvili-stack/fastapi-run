from fastapi import APIRouter, UploadFile, File

from app.api.invoice_parser import parse_invoice_pdf
from app.api.transaction_classifier import classify
from app.api.journal_generator import generate_draft
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/invoice", tags=["invoice"])


@router.post("/parse")
async def parse_invoice(file: UploadFile = File(...)):
    try:
        content = await file.read()

        if not (file.filename or "").lower().endswith(".pdf"):
            return error_response("Only PDF supported", "FORMAT_ERROR", "Upload .pdf file")

        parsed = parse_invoice_pdf(content)

        invoice_number = parsed.get("invoice_number") or ""
        partner = parsed.get("partner") or ""
        total_amount = parsed.get("total_amount")
        invoice_date = parsed.get("invoice_date")

        desc_parts = ["invoice"]
        if invoice_number:
            desc_parts.append(str(invoice_number))
        if partner:
            desc_parts.append(str(partner))
        desc = " ".join(desc_parts).strip()

        cl = classify(
            description=desc,
            paid_out=total_amount,
            partner=partner,
        )

        draft = generate_draft(
            {
                "description": f"Invoice {invoice_number}".strip(),
                "partner": partner,
                "amount": float(total_amount or 0),
                "date": invoice_date,
                "source_type": "pdf",
            },
            cl,
        )

        draft["classification_source"] = cl.get("source")
        draft["pattern_matched_on"] = cl.get("pattern_matched_on")
        draft["pattern_support_count"] = cl.get("pattern_support_count")
        draft["pattern_similarity"] = cl.get("pattern_similarity")
        draft["pattern_value_used"] = cl.get("pattern_value_used")
        draft["pattern_days_since_seen"] = cl.get("pattern_days_since_seen")
        draft["pattern_recency_penalty"] = cl.get("pattern_recency_penalty")
        draft["autopilot_decision"] = cl.get("autopilot_eligible")
        draft["autopilot_reason"] = cl.get("autopilot_reason")
        draft["approved_by_mode"] = "autopilot" if cl.get("autopilot_eligible") else "manual_review"

        return ok_response(
            "Invoice parsed",
            {
                "parsed": parsed,
                "classification": cl,
                "journal_draft": draft,
            },
        )

    except Exception as e:
        return error_response("Parse failed", "PARSE_ERROR", str(e))