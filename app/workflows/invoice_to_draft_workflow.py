def run_invoice_to_draft_workflow(payload: dict) -> dict:
    return {
        "ok": True,
        "stage": "invoice_workflow_ready",
        "payload": payload,
    }