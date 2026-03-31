def run_chat_action_workflow(payload: dict) -> dict:
    return {
        "ok": True,
        "stage": "chat_workflow_ready",
        "payload": payload,
    }