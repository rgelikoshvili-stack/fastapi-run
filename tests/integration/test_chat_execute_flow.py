def test_chat_execute_flow():
    from app.workflows.chat_action_workflow import run_chat_action_workflow

    result = run_chat_action_workflow({
        "action": {"action": "approval.approve"},
        "draft_id": 1
    })

    assert result is not None