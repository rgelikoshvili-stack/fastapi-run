"""Sprint 1 hardening: bank/payment AI tools are wired into chat orchestration."""

from app.api.services.ai_orchestrator_service import (
    _extract_tool_params,
    _format_tool_results,
    _select_tools,
)


def test_bank_intent_selects_bank_and_payment_tools():
    tools = _select_tools("რომელ ინვოისზე მოვიდა თანხა INV-2026-100?", None, {"bank", "invoices"})

    assert "get_bank_transactions" in tools
    assert "get_payment_status" in tools


def test_unreconciled_question_selects_bank_transactions_without_bank_keyword():
    tools = _select_tools("რომელი გადახდა ვერ დაემთხვა?", None, {"approval"})

    assert "get_bank_transactions" in tools


def test_extract_tool_params_reads_invoice_number_and_unreconciled_flag():
    params = _extract_tool_params("რომელი გადახდა ვერ დაემთხვა ინვოისზე INV-2026-100?", None)

    assert params["invoice_number"] == "INV-2026-100"
    assert params["unreconciled_only"] is True


def test_format_tool_results_includes_top_level_bank_tool_payloads():
    block = _format_tool_results({
        "get_payment_status": {
            "payment_status": "გადახდილია",
            "expected_amount": 1500.0,
            "paid_amount": 1500.0,
            "matched_bank_transactions": [{"id": "BT-1", "amount": 1500.0}],
        },
        "get_bank_transactions": {
            "count": 1,
            "unreconciled_in_results": 0,
            "transactions": [{"id": "BT-1", "is_reconciled": True}],
        },
    })

    assert "payment_status: გადახდილია" in block
    assert "matched_bank_transactions" in block
    assert "transactions" in block
