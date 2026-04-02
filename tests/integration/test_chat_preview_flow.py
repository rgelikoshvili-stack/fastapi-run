def test_chat_preview_flow():
    from app.workflows.chat_action_workflow import run_chat_action_workflow

    result = run_chat_action_workflow({
        "action": {"mode": "preview"}
    })

    assert result["ok"] is True