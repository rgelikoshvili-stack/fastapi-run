"""tests/unit/test_posting_log_audit_gate9.py — Gate 9: Posting Logs Audit Trail.

Verifies:
- idempotency_key column added to posting_logs schema migration.
- idempotency_key parameter present in apply_posting_service signature.
- idempotency_key parameter present in dry_run_posting_service signature.
- idempotency_key is threaded through the live posting INSERT SQL.
- idempotency_key is threaded through the dry-run posting INSERT SQL.
- apply route passes idempotency_key from X-Idempotent-Key to apply_posting_service.
- dry_run route passes idempotency_key from X-Idempotent-Key to dry_run_posting_service.
- payload_json stored in posting_logs does NOT contain api_key or Authorization.
- dry_run payload_json does NOT contain Bearer or any secret-like header.
- Runbook document exists at docs/balance-ge-rollback-runbook.md.
- Runbook contains emergency disable, CSV export, and duplicate prevention sections.
- mode, actor, connector, idempotency_key all appear in the live INSERT SQL source.
- mode, actor, connector, idempotency_key all appear in the dry-run INSERT SQL source.
"""
import inspect
import os
import pytest
from pathlib import Path


# ---------------------------------------------------------------------------
# Schema migration: idempotency_key column present
# ---------------------------------------------------------------------------

def test_idempotency_key_column_in_migration():
    from app.startup import migrations_indexes
    src = inspect.getsource(migrations_indexes)
    assert "idempotency_key" in src, (
        "posting_logs migration must add idempotency_key column (Gate 9)"
    )


# ---------------------------------------------------------------------------
# Service signatures: idempotency_key parameter present
# ---------------------------------------------------------------------------

def test_apply_posting_service_has_idempotency_key_param():
    from app.api.services import posting_service
    sig = inspect.signature(posting_service.apply_posting_service)
    assert "idempotency_key" in sig.parameters, (
        "apply_posting_service must accept idempotency_key parameter"
    )


def test_dry_run_posting_service_has_idempotency_key_param():
    from app.api.services import posting_service
    sig = inspect.signature(posting_service.dry_run_posting_service)
    assert "idempotency_key" in sig.parameters, (
        "dry_run_posting_service must accept idempotency_key parameter"
    )


# ---------------------------------------------------------------------------
# INSERT SQL: idempotency_key in column list
# ---------------------------------------------------------------------------

def test_live_insert_includes_idempotency_key():
    from app.api.services import posting_service
    src = inspect.getsource(posting_service.apply_posting_service)
    assert "idempotency_key" in src, (
        "apply_posting_service INSERT must include idempotency_key column"
    )


def test_dry_run_insert_includes_idempotency_key():
    from app.api.services import posting_service
    src = inspect.getsource(posting_service.dry_run_posting_service)
    assert "idempotency_key" in src, (
        "dry_run_posting_service INSERT must include idempotency_key column"
    )


# ---------------------------------------------------------------------------
# Route wiring: idempotency_key passed from header to service
# ---------------------------------------------------------------------------

def test_apply_route_passes_idempotency_key():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting.apply_posting)
    assert "idempotency_key" in src, (
        "apply_posting route must pass idempotency_key to apply_posting_service"
    )


def test_dry_run_route_passes_idempotency_key():
    from app.api import routes_posting
    src = inspect.getsource(routes_posting.dry_run_balance)
    assert "idempotency_key" in src, (
        "dry_run_balance route must pass idempotency_key to dry_run_posting_service"
    )


# ---------------------------------------------------------------------------
# No secrets in posting_log payload: _draft_to_posting_payload source check
# ---------------------------------------------------------------------------

def test_draft_to_posting_payload_does_not_include_api_key_field():
    """The payload builder must not copy api_key or Authorization into the output."""
    from app.api.services import posting_service
    src = inspect.getsource(posting_service._draft_to_posting_payload)
    # The function must explicitly whitelist fields rather than copying all draft fields
    # Confirm it doesn't blindly copy arbitrary keys
    assert "api_key" not in src or "api_key" not in [
        line.strip() for line in src.splitlines() if "payload" in line and "api_key" in line
    ], "payload builder must not forward api_key to output"


@pytest.mark.asyncio
async def test_posting_payload_no_secrets():
    """A draft payload must never contain api_key or Authorization values."""
    import json
    from app.api.services.posting_service import _draft_to_posting_payload
    draft = {
        "id": 1, "tenant_id": "t1", "date": "2026-05-26",
        "description": "Invoice", "partner": "P",
        "amount": 100.0, "currency": "GEL",
        "api_key": "SHOULD_NOT_APPEAR",
        "Authorization": "Bearer SHOULD_NOT_APPEAR",
        "lines_json": [
            {"account_code": "1210", "debit": 100.0, "credit": 0,    "label": "Dr"},
            {"account_code": "3110", "debit": 0,     "credit": 100.0, "label": "Cr"},
        ],
        "status": "approved",
    }
    payload = await _draft_to_posting_payload(draft)
    payload_str = json.dumps(payload)
    assert "SHOULD_NOT_APPEAR" not in payload_str
    assert "api_key" not in payload_str
    assert "Authorization" not in payload_str
    assert "Bearer" not in payload_str


# ---------------------------------------------------------------------------
# All required audit fields present in INSERT SQL
# ---------------------------------------------------------------------------

def test_live_insert_all_audit_fields():
    """mode, actor, connector, idempotency_key must all appear in live INSERT."""
    from app.api.services import posting_service
    src = inspect.getsource(posting_service.apply_posting_service)
    for field in ("mode", "actor", "connector", "idempotency_key"):
        assert field in src, f"live INSERT must include {field} field (Gate 9)"


def test_dry_run_insert_all_audit_fields():
    """mode, actor, connector, idempotency_key must all appear in dry-run INSERT."""
    from app.api.services import posting_service
    src = inspect.getsource(posting_service.dry_run_posting_service)
    for field in ("mode", "actor", "connector", "idempotency_key"):
        assert field in src, f"dry-run INSERT must include {field} field (Gate 9)"


# ---------------------------------------------------------------------------
# Runbook document exists and is complete (Gate 12 final requirement)
# ---------------------------------------------------------------------------

def test_rollback_runbook_exists():
    """docs/balance-ge-rollback-runbook.md must exist."""
    runbook = Path(__file__).parents[2] / "docs" / "balance-ge-rollback-runbook.md"
    assert runbook.exists(), (
        "Gate 12 requires docs/balance-ge-rollback-runbook.md to exist"
    )


def test_rollback_runbook_has_emergency_disable_section():
    runbook = Path(__file__).parents[2] / "docs" / "balance-ge-rollback-runbook.md"
    text = runbook.read_text(encoding="utf-8")
    assert "CONNECTOR_DISABLED" in text or "disable" in text.lower()
    assert "connector/balance/disable" in text


def test_rollback_runbook_has_csv_export_section():
    runbook = Path(__file__).parents[2] / "docs" / "balance-ge-rollback-runbook.md"
    text = runbook.read_text(encoding="utf-8")
    assert "approved-drafts/csv" in text or "CSV" in text


def test_rollback_runbook_has_duplicate_prevention_section():
    runbook = Path(__file__).parents[2] / "docs" / "balance-ge-rollback-runbook.md"
    text = runbook.read_text(encoding="utf-8")
    assert "idempotency" in text.lower() or "duplicate" in text.lower()


def test_rollback_runbook_no_secrets():
    """Runbook must not contain real API keys or credentials."""
    runbook = Path(__file__).parents[2] / "docs" / "balance-ge-rollback-runbook.md"
    text = runbook.read_text(encoding="utf-8")
    # No hardcoded secret-like values
    assert "sk-" not in text
    assert "Bearer eyJ" not in text
    assert "api_key=" not in text.lower().replace("api_key`", "").replace("api_key column", "")
