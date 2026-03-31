from app.workflows.bank_to_draft_workflow import run_bank_to_draft_workflow


def test_bank_to_draft_workflow_validation():
    payload = {
        "date": "2026-03-31",
        "description": "Salary payment",
        "partner": "My Company",
        "amount": 2500,
    }

    result = run_bank_to_draft_workflow(payload)
    assert result["ok"] is True
    assert result["stage"] == "validated"