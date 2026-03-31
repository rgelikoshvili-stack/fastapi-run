from app.api.invoice_parser import parse_invoice_pdf
from app.api.transaction_classifier import classify
from app.api.journal_generator import generate_draft

from app.services.preview_service import build_draft_preview
from app.workflows.bank_to_draft_workflow import run_bank_to_draft_workflow
from app.workflows.invoice_to_draft_workflow import run_invoice_to_draft_workflow
from app.workflows.chat_action_workflow import run_chat_action_workflow


def bridge_invoice_payload(payload: dict) -> dict:
    content = payload.get("content", b"")
    filename = (payload.get("filename") or "").lower()

    if not filename.endswith(".pdf"):
        return {
            "ok": False,
            "message": "Only PDF supported",
            "data": None,
            "error": "FORMAT_ERROR",
        }

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
    draft["approved_by_mode"] = (
        "autopilot" if cl.get("autopilot_eligible") else "manual_review"
    )

    workflow_result = run_invoice_to_draft_workflow(
        {
            "filename": payload.get("filename"),
            "parsed": parsed,
            "classification": cl,
            "journal_draft": draft,
        }
    )

    return {
        "ok": True,
        "message": "Invoice workflow processed",
        "data": {
            "workflow": workflow_result,
            "parsed": parsed,
            "classification": cl,
            "journal_draft": draft,
            "preview": build_draft_preview(draft),
        },
        "error": None,
    }


def bridge_chat_payload(payload: dict) -> dict:
    result = run_chat_action_workflow(payload)
    return {
        "ok": result.get("ok", False),
        "message": "Chat workflow processed",
        "data": result,
        "error": None if result.get("ok") else result.get("error", "WORKFLOW_ERROR"),
    }


def bridge_bank_payload(payload: dict) -> dict:
    result = run_bank_to_draft_workflow(payload)
    return {
        "ok": result.get("ok", False),
        "message": "Bank workflow processed",
        "data": result,
        "error": None if result.get("ok") else result.get("error", "WORKFLOW_ERROR"),
    }


def build_preview_response(payload: dict) -> dict:
    preview = build_draft_preview(payload)
    return {
        "ok": True,
        "message": "Preview ready",
        "data": preview,
        "error": None,
    }