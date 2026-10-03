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


def test_rsge_mutation_gate_requires_flags_rbac_and_approval(monkeypatch):
    from app.api.services import rsge_config as cfg

    for key in [
        "RSGE_ENABLED", "RSGE_CONNECTOR_ENABLED", "RSGE_READ_ONLY",
        "RSGE_DRY_RUN", "RSGE_LIVE_ACTIONS_ENABLED", "RSGE_ALLOW_CONFIRM",
        "RSGE_FINAL_APPROVAL_RECORDED",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(PermissionError, match="RSGE_ACTION_BLOCKED"):
        cfg.require_action("confirm", rbac_allowed=True, approval_recorded=True)

    monkeypatch.setenv("RSGE_ENABLED", "true")
    monkeypatch.setenv("RSGE_READ_ONLY", "false")
    monkeypatch.setenv("RSGE_DRY_RUN", "false")
    monkeypatch.setenv("RSGE_LIVE_ACTIONS_ENABLED", "true")
    monkeypatch.setenv("RSGE_ALLOW_CONFIRM", "true")
    monkeypatch.setenv("RSGE_FINAL_APPROVAL_RECORDED", "true")

    with pytest.raises(PermissionError, match="RSGE_ACTION_BLOCKED"):
        cfg.require_action("confirm", rbac_allowed=False, approval_recorded=True)
    with pytest.raises(PermissionError, match="RSGE_ACTION_BLOCKED"):
        cfg.require_action("confirm", rbac_allowed=True, approval_recorded=False)
    cfg.require_action("confirm", rbac_allowed=True, approval_recorded=True)


def test_rsge_mutation_gate_rejects_unknown_actions():
    from app.api.services.rsge_config import require_action

    with pytest.raises(PermissionError, match="RSGE_ACTION_BLOCKED"):
        require_action("unknown", rbac_allowed=True, approval_recorded=True)


def test_live_rsge_sync_route_is_gate_blocked_by_default(monkeypatch):
    from fastapi import HTTPException, Request
    from app.api import routes_rs_ge as route

    for key in [
        "RSGE_ENABLED", "RSGE_READ_ONLY", "RSGE_DRY_RUN",
        "RSGE_LIVE_ACTIONS_ENABLED", "RSGE_ALLOW_WAYBILL_ACTIONS",
        "RSGE_FINAL_APPROVAL_RECORDED",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(route, "require_permission", lambda *args: None)

    request = Request({
        "type": "http", "method": "POST", "path": "/rs-ge/sync",
        "headers": [], "state": {"tenant_id": "tenant-a", "role": "admin"},
    })
    with pytest.raises(HTTPException) as exc:
        asyncio.run(route.sync_waybills_from_rsge(
            route.SyncPayload(operator_confirmed=True), request,
        ))
    assert exc.value.status_code == 403


def test_rsge_credentials_route_does_not_write_plaintext_password():
    source = read_source("app/api/routes_rsge_credentials.py")

    assert "CredentialVaultService" in source
    assert "raw_value=body.password" in source
    assert "password             = '[stored-in-vault]'" in source
    assert "ALTER COLUMN password DROP NOT NULL" in source
    assert "password             TEXT NOT NULL" not in source


def test_rsge_legacy_not_null_schema_save_is_vault_first_and_scrubs_old_password(monkeypatch):
    from fastapi import Request
    from app.api import routes_rsge_credentials as route

    events = []

    class FakeConnection:
        async def execute(self, sql, *args):
            events.append(("execute", sql, args))

    class FakeConnectionContext:
        async def __aenter__(self):
            return FakeConnection()

        async def __aexit__(self, *exc):
            return False

    class FakeVault:
        async def save_credential(self, conn, **kwargs):
            events.append(("vault", kwargs))
            return {"configured": True, "masked_hint": "****test"}

    monkeypatch.setattr(route, "get_conn", lambda: FakeConnectionContext())
    monkeypatch.setattr(route, "CredentialVaultService", FakeVault)
    monkeypatch.setattr(route, "require_permission", lambda *args: None)

    request = Request({
        "type": "http", "method": "POST", "path": "/rsge-credentials/save",
        "headers": [], "state": {"tenant_id": "tenant-a", "user_id": "operator-a"},
    })
    result = asyncio.run(route.save_creds(
        route.RsgeCredsPayload(username="operator", password="fake-test-only-secret"),
        request,
    ))

    assert result["data"]["credential_status"] == "active"
    vault_event = next(i for i, event in enumerate(events) if event[0] == "vault")
    insert_event = next(i for i, event in enumerate(events) if event[0] == "execute" and "INSERT INTO tenant_rsge_credentials" in event[1])
    assert vault_event < insert_event
    insert_sql, insert_args = events[insert_event][1:]
    assert "password             = '[stored-in-vault]'" in insert_sql
    assert "'[stored-in-vault]'" in insert_sql
    assert "fake-test-only-secret" not in insert_args
    assert "fake-test-only-secret" not in str(result)


def test_rsge_vault_migration_marks_legacy_rows_for_rotation_without_copying_secrets():
    migration = read_source("app/storage/migrations/012_rsge_credentials_vault_migration.sql")
    assert "credential_status = 'rotation_required'" in migration
    assert "DROP NOT NULL" in migration
    assert "UPDATE tenant_rsge_credentials" in migration
    assert "SET password" not in migration


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

    with pytest.raises(ValueError, match="FX rate"):
        asyncio.run(_draft_to_posting_payload(draft))


@pytest.mark.parametrize("bad_rate", ["0", "-1", "NaN"])
def test_non_gel_fx_rejects_nonpositive_or_nonfinite_rate(monkeypatch, bad_rate):
    async def bad_rate_lookup(*args, **kwargs):
        from decimal import Decimal
        return Decimal(bad_rate)

    import app.api.services.currency_service as currency_service
    from app.api.services.posting_service import _draft_to_posting_payload

    monkeypatch.setattr(currency_service, "get_rate_async", bad_rate_lookup)
    draft = {"id": 2, "tenant_id": "tenant-a", "date": "2026-08-14",
             "amount": "100", "currency": "USD", "lines": []}
    with pytest.raises(ValueError, match="FX rate"):
        asyncio.run(_draft_to_posting_payload(draft))


def test_currency_helper_raises_instead_of_returning_zero_for_unknown_currency(monkeypatch):
    import app.api.services.currency_service as currency_service

    monkeypatch.setattr(currency_service, "get_db", lambda: (_ for _ in ()).throw(RuntimeError("offline")))
    with pytest.raises(currency_service.CurrencyRateNotFound, match="FX_RATE_MISSING"):
        currency_service._rate_to_gel("ZZZ")


def test_ledger_writer_rejects_zero_rate_instead_of_coercing_to_one():
    from app.api.services.posting_service import _write_ledger_entries

    class EmptyConn:
        async def fetchval(self, *args):
            return None

    with pytest.raises(ValueError, match="FX_RATE_INVALID"):
        asyncio.run(_write_ledger_entries(
            EmptyConn(), {"id": 2, "date": "2026-08-14", "currency": "USD", "lines": []},
            {"exchange_rate": 0}, "tenant-a", "test", "hash",
        ))


def test_ai_document_and_triangle_queries_are_tenant_scoped(monkeypatch):
    from app.api.services import ai_tool_registry as registry

    class FakeConn:
        def __init__(self):
            self.queries = []

        async def fetch(self, sql, *args):
            self.queries.append((sql, args))
            assert "tenant_id = $1" in sql or "tm.tenant_id = $1" in sql
            assert args[0] == "tenant-a"
            # Simulate a mixed-tenant backing set and enforce the bound tenant predicate.
            mixed_rows = [
                {"tenant_id": "tenant-a", "id": 1, "number": "WB-A", "status": "posted"},
                {"tenant_id": "tenant-b", "id": 2, "number": "WB-B", "status": "posted"},
            ]
            return [row for row in mixed_rows if row["tenant_id"] == args[0]]

    class Context:
        def __init__(self, conn): self.conn = conn
        async def __aenter__(self): return self.conn
        async def __aexit__(self, *exc): return False

    conn = FakeConn()
    monkeypatch.setattr(registry, "get_conn", lambda: Context(conn))

    status = asyncio.run(registry._get_rsge_document_status({"document_number": "WB"}, "tenant-a"))
    triangle = asyncio.run(registry._get_triangle_match_status({}, "tenant-a"))

    assert conn.queries
    assert all(args[0] == "tenant-a" for _, args in conn.queries)
    assert all("tenant-b" not in str(row) for row in status["documents"] + triangle["matches"])


def test_accounting_risk_summary_binds_tenant_for_every_query(monkeypatch):
    from app.api.services import ai_tool_registry as registry

    class FakeConn:
        def __init__(self): self.queries = []
        async def fetchval(self, sql, *args):
            self.queries.append((sql, args))
            return 0
        async def fetchrow(self, sql, *args):
            self.queries.append((sql, args))
            return None

    class Context:
        def __init__(self, conn): self.conn = conn
        async def __aenter__(self): return self.conn
        async def __aexit__(self, *exc): return False

    conn = FakeConn()
    monkeypatch.setattr(registry, "get_conn", lambda: Context(conn))
    result = asyncio.run(registry._get_accounting_risk_summary({}, "tenant-a"))

    assert len(conn.queries) == 6
    assert all(args[0] == "tenant-a" for _, args in conn.queries)
    assert all("tenant_id = $1" in sql or "w.tenant_id = $1" in sql or "jd.tenant_id = $1" in sql
               for sql, _ in conn.queries)
    assert result["risk_count"] == 0
    missing_fx_sql = next(sql for sql, _ in conn.queries if "exchange_rates" in sql)
    assert "from_code" in missing_fx_sql and "to_code" in missing_fx_sql
    assert "currency_rates" not in missing_fx_sql


def test_claude_accounting_context_missing_fx_uses_currency_service_schema():
    source = read_source("app/api/routes_claude_chat.py")
    assert "FROM exchange_rates cr" in source
    assert "cr.from_code" in source
    assert "cr.to_code" in source
    assert "FROM currency_rates cr" not in source


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
