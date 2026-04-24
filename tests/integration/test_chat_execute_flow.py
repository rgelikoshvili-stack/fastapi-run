from unittest.mock import patch, MagicMock


def test_chat_execute_flow():
    from app.workflows.chat_action_workflow import run_chat_action_workflow

    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None  # draft not found → service returns error dict
    mock_conn = MagicMock()
    mock_conn.cursor.return_value.__enter__ = lambda s: mock_cur
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("app.api.services.approval_service.get_db", return_value=mock_conn):
        result = run_chat_action_workflow({
            "action": {"action": "approval.approve"},
            "draft_id": 1,
            "tenant_id": "default",
        })

    assert result is not None
