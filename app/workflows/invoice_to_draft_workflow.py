from app.api.services.context_engine import build_context
from app.api.services.memory_priority_engine import merge_memory_sources
from app.api.services.qa_engine import evaluate_decision
from app.api.services.confidence_engine import adjust_confidence


def run_invoice_to_draft_workflow(payload: dict) -> dict:
    parsed = payload.get("parsed", {}) or {}
    classification = payload.get("classification", {}) or {}
    journal_draft = payload.get("journal_draft", {}) or {}

    context_payload = {
        "description": journal_draft.get("description") or parsed.get("raw_text") or "",
        "partner": journal_draft.get("partner") or parsed.get("partner") or "",
    }

    # 🧠 CONTEXT
    context = build_context(context_payload)

    # 🧠 MEMORY PRIORITY
    memory_decision = merge_memory_sources(context, classification)

    # 🧠 QA CHECK
    qa = evaluate_decision(journal_draft)

    # 🧠 ADAPTIVE CONFIDENCE
    adjusted_conf = adjust_confidence(
        classification.get("confidence", 0),
        context,
        qa
    )

    return {
        "ok": True,
        "stage": "invoice_workflow_ready",
        "payload": payload,
        "context": context,
        "memory_decision": memory_decision,
        "qa": qa,
        "adjusted_confidence": adjusted_conf,
        "summary": {
            "invoice_number": parsed.get("invoice_number"),
            "partner": parsed.get("partner"),
            "total_amount": parsed.get("total_amount"),
            "extraction_confidence": parsed.get("extraction_confidence"),
            "review_required": parsed.get("review_required"),

            "classification_source": classification.get("source"),
            "account_code": classification.get("account_code"),

            "draft_status": journal_draft.get("status"),

            "context_used": context.get("context_used"),

            "memory_source": memory_decision.get("source"),
            "memory_confidence": memory_decision.get("confidence"),

            "qa_score": qa.get("score"),
            "qa_recommendation": qa.get("recommendation"),

            "final_confidence": adjusted_conf,
        },
    }