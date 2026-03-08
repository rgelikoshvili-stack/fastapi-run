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
        if not file.filename.lower().endswith(".pdf"):
            return error_response("Only PDF supported", "FORMAT_ERROR", "Upload .pdf file")
        parsed = parse_invoice_pdf(content)
        # auto-classify
        desc = f"software service invoice {parsed.get('invoice_number','') or ''}"
        cl = classify(
            description=desc,
            paid_out=parsed.get("total_amount"),
            partner=parsed.get("partner") or ""
        )
        draft = generate_draft({
            "description": f"Invoice {parsed.get('invoice_number','') or ''}",
            "partner": parsed.get("partner"),
            "amount": float(parsed.get("total_amount") or 0),
            "date": parsed.get("invoice_date"),
            "source_type": "pdf"
        }, cl)
        return ok_response("Invoice parsed", {
            "parsed": parsed,
            "classification": cl,
            "journal_draft": draft
        })
    except Exception as e:
        return error_response("Parse failed", "PARSE_ERROR", str(e))
