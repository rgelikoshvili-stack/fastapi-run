import asyncio
import importlib
import os
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def read_source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_claude_approve_tool_is_preview_only():
    from app.api.routes_claude_chat import _tool_approve_draft

    result = asyncio.run(_tool_approve_draft({"draft_id": 123}, "tenant-a"))

    assert result["approval_required"] is True
    assert result["success"] is False
    assert result["next_endpoint"] == "/api/approval/approve/123"

    source = read_source("app/api/routes_claude_chat.py")
    assert "SET status = 'approved', approved_by = 'chat_ai'" not in source
    assert "UPDATE journal_drafts" not in source


def test_rsge_config_defaults_are_safe(monkeypatch):
    for key in [
        "RSGE_ENABLED",
        "RSGE_CONNECTOR_ENABLED",
        "RSGE_LIVE_ACTIONS_ENABLED",
        "RSGE_READ_ONLY",
        "RSGE_DRY_RUN",
        "RSGE_TEST_MODE",
        "RSGE_ALLOW_CONFIRM",
        "RSGE_ALLOW_REJECT",
        "RSGE_ALLOW_CANCEL",
        "RSGE_ALLOW_CORRECT",
        "RSGE_ALLOW_ACTIVATE",
        "RSGE_ALLOW_WAYBILL_ACTIONS",
        "RSGE_FINAL_APPROVAL_RECORDED",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    cfg = importlib.reload(importlib.import_module("app.api.services.rsge_config"))

    assert cfg.is_enabled() is False
    assert cfg.live_actions_enabled() is False
    assert cfg.read_only() is True
    assert cfg.dry_run() is True
    assert cfg.allow_action("confirm") is False
    assert cfg.allow_action("reject") is False


def test_rsge_config_requires_all_live_gates(monkeypatch):
    cfg = importlib.import_module("app.api.services.rsge_config")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("RSGE_ENABLED", "true")
    monkeypatch.setenv("RSGE_READ_ONLY", "false")
    monkeypatch.setenv("RSGE_DRY_RUN", "false")
    monkeypatch.setenv("RSGE_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("RSGE_ALLOW_CONFIRM", "true")

    assert cfg.allow_action("confirm") is False

    monkeypatch.setenv("RSGE_FINAL_APPROVAL_RECORDED", "true")
    assert cfg.allow_action("confirm") is True
    assert cfg.allow_action("cancel") is False


def test_rsge_credentials_route_does_not_write_plaintext_password():
    source = read_source("app/api/routes_rsge_credentials.py")

    assert "CredentialVaultService" in source
    assert "raw_value=body.password" in source
    assert "password     TEXT NOT NULL" not in source
    assert "INSERT INTO tenant_rsge_credentials (tenant_id, username, password" not in source
    assert "password = EXCLUDED.password" not in source


def test_non_gel_fx_missing_blocks_posting(monkeypatch):
    async def missing_rate(*args, **kwargs):
        raise RuntimeError("missing")

    import app.api.services.currency_service as currency_service
    from app.api.services.posting_service import _draft_to_posting_payload

    monkeypatch.setattr(currency_service, "get_rate_async", missing_rate)

    draft = {
        "id": 1,
        "tenant_id": "tenant-a",
        "date": "2026-08-14",
        "description": "USD invoice",
        "amount": "100.00",
        "currency": "USD",
        "lines": [],
    }

    with pytest.raises(ValueError, match="FX_RATE_MISSING"):
        asyncio.run(_draft_to_posting_payload(draft))


def test_gel_fx_rate_remains_one():
    from app.api.services.posting_service import _draft_to_posting_payload

    draft = {
        "id": 1,
        "tenant_id": "tenant-a",
        "date": "2026-08-14",
        "description": "GEL invoice",
        "amount": "100.00",
        "currency": "GEL",
        "lines": [],
    }

    payload = asyncio.run(_draft_to_posting_payload(draft))
    assert payload["exchange_rate"] == 1.0
    assert payload["amount_gel"] == 100.0


def test_ai_tool_registry_includes_rsge_evidence_visibility():
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS, _TOOL_MAP

    assert "get_rsge_document_status" in TOOL_DESCRIPTIONS
    assert "get_triangle_match_status" in TOOL_DESCRIPTIONS
    assert "get_accounting_risk_summary" in TOOL_DESCRIPTIONS
    assert "get_rsge_document_status" in _TOOL_MAP
    assert "get_triangle_match_status" in _TOOL_MAP
    assert "get_accounting_risk_summary" in _TOOL_MAP

    source = read_source("app/api/services/ai_tool_registry.py")
    for table in [
        "FROM waybills",
        "FROM tax_invoices",
        "FROM commercial_invoices",
        "FROM evidence_bundles",
        "FROM triangle_matches",
    ]:
        assert table in source
