"""Coverage for the Task 4 backend contract and observability hardening."""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from app.api.response_utils import ok_response, error_response


def test_batch_action_returns_per_item_results_and_is_idempotent():
    from app.api import routes_approval

    body = routes_approval.BatchActionRequest(action="approve", draft_ids=[11, 12])
    request = MagicMock()
    request.state.user_id = "user-1"
    request.state.tenant_id = "tenant-a"
    request.state.role = "admin"
    request.state.authenticated = True
    request.headers = {"X-Idempotent-Key": "batch-key-001"}

    approve_results = [
        ok_response("Draft approved", {"id": 11, "status": "approved", "tenant_id": "tenant-a"}),
        error_response("Approve blocked", "APPROVE_BLOCKED", "Draft 12 is locked"),
    ]

    target = getattr(routes_approval.batch_action, "__wrapped__", routes_approval.batch_action)

    with patch("app.api.routes_approval.approve_draft_service", side_effect=approve_results), \
         patch("app.api.routes_approval.reject_draft_service"), \
         patch("app.api.routes_approval.idempotency_check", AsyncMock(return_value=None)), \
         patch("app.api.routes_approval.idempotency_store", AsyncMock()) as store_mock, \
         patch("app.api.routes_approval.cache_clear_prefix"), \
         patch("app.api.routes_approval.structured_log"):
        result = asyncio.run(target(body, request))

    assert result["ok"] is True
    assert result["data"]["affected"] == 1
    assert len(result["data"]["results"]) == 2
    assert result["data"]["results"][0]["ok"] is True
    assert result["data"]["results"][1]["ok"] is False
    assert result["data"]["results"][1]["error"]["code"] == "APPROVE_BLOCKED"
    store_mock.assert_awaited_once()


def test_structured_log_helper_filters_sensitive_fields():
    from app.api.observability import structured_log
    import logging

    captured = []

    class _Handler(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    logger = logging.getLogger("test_structured_log_helper")
    logger.handlers = []
    logger.propagate = False
    logger.addHandler(_Handler())
    logger.setLevel(logging.INFO)

    structured_log(logger, logging.INFO, "sample_event", tenant_id="tenant-a", token="secret", result="success")

    assert captured
    assert "\"event\": \"sample_event\"" in captured[0]
    assert "\"tenant_id\": \"tenant-a\"" in captured[0]
    assert "secret" not in captured[0]


def test_audit_service_uses_logger_not_print():
    import app.api.audit_service as mod

    src = inspect.getsource(mod)
    assert "print(f\"Audit log error" not in src
    assert "log.exception" in src


def test_permission_denial_logging_hooks_exist():
    import app.api.middleware.rbac_middleware as rbac
    import app.api.middleware.auth_middleware as auth

    rbac_src = inspect.getsource(rbac)
    auth_src = inspect.getsource(auth)
    assert "permission_denied" in rbac_src
    assert "auth_denied" in rbac_src
    assert "auth_token_missing" in auth_src
    assert "auth_token_invalid" in auth_src


def test_autopilot_approval_emits_structured_logs():
    import app.api.services.approval_service as mod

    src = inspect.getsource(mod.autopilot_approve_service)
    assert "structured_log(" in src
    assert "autopilot_approval_started" in src
    assert "autopilot_approval_item_completed" in src
    assert "autopilot_approval_item_failed" in src
    assert "autopilot_approval_completed" in src
    assert "token" not in src.lower()


def test_batch_completion_log_includes_per_item_counts():
    from app.api import routes_approval

    src = inspect.getsource(routes_approval.batch_action)
    assert "approval_batch_completed" in src
    assert "succeeded_count" in src
    assert "failed_count" in src
    assert "skipped_count" in src
    assert "BATCH_PARTIAL_FAILURE" in src


def test_hardening_doc_exists():
    assert Path("docs/code-quality-hardening.md").exists()


def test_inventory_receive_purchase_order_creates_journal_draft_hook():
    import app.api.services.inventory_service as mod

    src = inspect.getsource(mod.receive_purchase_order)
    assert "create_journal_draft" in src
    assert "draft_ids" in src


def test_purchase_order_detail_route_exists():
    import app.api.routes_inventory as mod

    src = inspect.getsource(mod)
    assert "/purchase-orders/{po_id}" in src
    assert "get_purchase_order_detail" in src


def test_shared_journal_draft_helper_persists_journal_entries():
    import app.api.services.posting_service as mod

    src = inspect.getsource(mod.create_journal_draft)
    assert "journal_entries" in src
    assert "_lines_to_journal_entries" in inspect.getsource(mod)


def test_sales_invoice_finalize_creates_journal_draft():
    import app.api.services.invoice_creator as mod

    src = inspect.getsource(mod.finalize)
    assert "INSERT INTO journal_drafts" in src
    assert "journal_draft_id" in src


def test_counterparties_route_exists():
    import app.api.routes_crm as mod

    src = inspect.getsource(mod)
    assert "/counterparties" in src
    assert "CounterpartyCreate" in src


def test_vat_register_route_exists():
    import app.api.routes_tax as mod

    src = inspect.getsource(mod)
    assert "vat-register" in src
    assert "VAT register" in src
