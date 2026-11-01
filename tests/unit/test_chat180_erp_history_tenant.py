"""ERP memory is tenant-owned learning evidence, never the posted ledger."""
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import db, routes_erp_memory as memory_routes, routes_erp_import as import_routes
from app.api import routes_erp_connectors as connector_routes
from app.api.services import erp_memory_service as memory, erp_import_service as imports
from app.api.services import erp_history_import_service as history


def request(role="accountant", tenant="t_alpha", signed="t_alpha", authenticated=True):
    result = Request({"type": "http", "method": "POST", "path": "/erp-memory/upsert", "headers": []})
    result.state.role = role
    result.state.authenticated = authenticated
    result.state.tenant_id = tenant
    result.state.auth_tenant_id = signed
    return result


@pytest.mark.parametrize("operation", ["upsert", "list", "import"])
@pytest.mark.parametrize("tenant", [None, "default", "t_beta"])
def test_unscoped_or_mismatched_services_do_not_open_database(monkeypatch, operation, tenant):
    opened = Mock(side_effect=AssertionError("database must not open"))
    monkeypatch.setattr(memory, "get_db", opened)
    monkeypatch.setattr(imports, "upsert_erp_posting_memory", opened)
    context = db.authenticated_tenant_context(None if tenant is None else "t_alpha")
    with context, pytest.raises(ValueError):
        if operation == "upsert":
            memory.upsert_erp_posting_memory(tenant_id=tenant)
        elif operation == "list":
            memory.list_erp_posting_memory(tenant_id=tenant)
        else:
            imports.import_erp_history([], tenant_id=tenant)
    opened.assert_not_called()


@pytest.mark.parametrize("tenant", [None, "default", "t_beta"])
def test_optional_classifier_memory_without_authority_is_absent(monkeypatch, tenant):
    opened = Mock(side_effect=AssertionError("database must not open"))
    monkeypatch.setattr(memory, "get_db", opened)
    with db.authenticated_tenant_context(None if tenant is None else "t_alpha"):
        assert memory.find_erp_memory_match(description="invoice", tenant_id=tenant) is None
    opened.assert_not_called()


@pytest.mark.parametrize("operation", ["upsert", "list", "import", "connector"])
@pytest.mark.parametrize("state", ["anonymous", "unsigned", "mismatch", "no_context"])
def test_routes_deny_missing_or_inconsistent_signed_scope(monkeypatch, operation, state):
    io = Mock(return_value={"ok": True})
    monkeypatch.setattr(memory_routes, "upsert_erp_posting_memory", io)
    monkeypatch.setattr(memory_routes, "list_erp_posting_memory", io)
    monkeypatch.setattr(import_routes, "import_erp_history", io)
    monkeypatch.setattr(connector_routes, "import_posted_history_from_connector", io)
    r = request(authenticated=state != "anonymous", signed=None if state == "unsigned" else "t_alpha",
                tenant="t_beta" if state == "mismatch" else "t_alpha")
    with db.authenticated_tenant_context(None if state == "no_context" else "t_alpha"):
        with pytest.raises(HTTPException) as exc:
            if operation == "upsert":
                memory_routes.upsert_memory(memory_routes.ErpMemoryUpsertRequest(), r)
            elif operation == "list":
                memory_routes.list_memory(r)
            elif operation == "import":
                import_routes.import_erp_history_json(import_routes.ErpImportRequest(items=[]), r)
            else:
                connector_routes.import_history(r, source_system="balance", mode="demo", date_from=None, date_to=None, limit=1)
        assert exc.value.status_code in (401, 403)
    io.assert_not_called()


def test_reader_can_list_own_memory_but_cannot_upsert(monkeypatch):
    read = Mock(return_value=[])
    write = Mock(return_value={"ok": True})
    monkeypatch.setattr(memory_routes, "list_erp_posting_memory", read)
    monkeypatch.setattr(memory_routes, "upsert_erp_posting_memory", write)
    with db.authenticated_tenant_context("t_alpha"):
        assert memory_routes.list_memory(request(role="viewer"), limit=12)["ok"]
        with pytest.raises(HTTPException) as exc:
            memory_routes.upsert_memory(memory_routes.ErpMemoryUpsertRequest(), request(role="viewer"))
        assert exc.value.status_code == 403
    read.assert_called_once_with(limit=12, tenant_id="t_alpha")
    write.assert_not_called()
    from app.api.policy.permission_map import match_permission
    assert match_permission("GET", "/erp-memory/list") == "posting:read"
    assert match_permission("POST", "/erp-memory/upsert") == "posting:write"


def test_routes_pass_only_verified_tenant_not_body_hint(monkeypatch):
    write = Mock(return_value={"ok": True})
    importer = Mock(return_value={"ok": True, "errors": []})
    connector = Mock(return_value={"ok": True, "errors": []})
    monkeypatch.setattr(memory_routes, "upsert_erp_posting_memory", write)
    monkeypatch.setattr(import_routes, "import_erp_history", importer)
    monkeypatch.setattr(connector_routes, "import_posted_history_from_connector", connector)
    with db.authenticated_tenant_context("t_alpha"):
        memory_routes.upsert_memory(memory_routes.ErpMemoryUpsertRequest.model_validate({"tenant_id": "t_beta"}), request())
        import_routes.import_erp_history_json(import_routes.ErpImportRequest.model_validate({"tenant_id": "t_beta", "items": []}), request())
        connector_routes.import_history(request(), source_system="balance", mode="demo", date_from=None, date_to=None, limit=1)
    assert write.call_args.kwargs["tenant_id"] == "t_alpha"
    assert importer.call_args.kwargs["tenant_id"] == "t_alpha"
    assert connector.call_args.kwargs["tenant_id"] == "t_alpha"


def test_import_propagates_tenant_and_redacts_failed_row(monkeypatch):
    write = Mock(side_effect=[{"ok": True}, RuntimeError("secret internal SQL detail")])
    monkeypatch.setattr(imports, "upsert_erp_posting_memory", write)
    rows = [{"external_entry_id": "a", "account_code": "1110", "tenant_id": "t_beta"},
            {"description": "private bank description"}]
    with db.authenticated_tenant_context("t_alpha"):
        result = imports.import_erp_history(rows, tenant_id="t_alpha")
    assert not result["ok"]
    assert result["inserted_or_updated"] == 1
    assert result["errors"] == [{"index": 2, "error": "ERP_MEMORY_UPSERT_FAILED"}]
    assert all(c.kwargs["tenant_id"] == "t_alpha" for c in write.call_args_list)


@pytest.mark.parametrize("source", ["balance", "1c", "oris"])
def test_demo_history_never_loads_credentials_calls_provider_or_persists(monkeypatch, source):
    monkeypatch.setenv("ONEC_ENDPOINT", "https://unused.example.test")
    io = Mock(side_effect=AssertionError("demo must not perform I/O"))
    monkeypatch.setattr(imports, "upsert_erp_posting_memory", io)
    monkeypatch.setattr("requests.get", io)
    monkeypatch.setattr("app.api.services.balance_credentials_service.get_balance_credentials_sync", io)
    with db.authenticated_tenant_context("t_alpha"):
        result = history.import_posted_history_from_connector(source, mode="demo", tenant_id="t_alpha")
    assert result["ok"] and result["simulated"] and not result["authoritative"]
    assert result["inserted_or_updated"] == 0
    io.assert_not_called()


@pytest.mark.parametrize("source", ["balance", "1c", "oris"])
def test_unverified_live_history_adapter_fails_before_io(monkeypatch, source):
    io = Mock(side_effect=AssertionError("unverified adapter must not open"))
    monkeypatch.setattr(imports, "upsert_erp_posting_memory", io)
    monkeypatch.setattr("requests.get", io)
    with db.authenticated_tenant_context("t_alpha"):
        with pytest.raises(ValueError, match="ERP_HISTORY_LIVE_ADAPTER_UNVERIFIED"):
            history.import_posted_history_from_connector(source, mode="real", tenant_id="t_alpha")
    io.assert_not_called()


def test_route_failures_are_redacted_and_partial_import_not_labelled_success(monkeypatch):
    failure = Mock(side_effect=RuntimeError("secret SQL password and bank description"))
    monkeypatch.setattr(memory_routes, "upsert_erp_posting_memory", failure)
    monkeypatch.setattr(memory_routes, "list_erp_posting_memory", failure)
    monkeypatch.setattr(import_routes, "import_erp_history", lambda **kw: {"ok": False, "errors": [{"index": 1, "error": "ERP_MEMORY_UPSERT_FAILED"}]})
    monkeypatch.setattr(connector_routes, "import_posted_history_from_connector", failure)
    with db.authenticated_tenant_context("t_alpha"):
        responses = [memory_routes.upsert_memory(memory_routes.ErpMemoryUpsertRequest(), request()),
                     memory_routes.list_memory(request()),
                     import_routes.import_erp_history_json(import_routes.ErpImportRequest(items=[]), request()),
                     connector_routes.import_history(request(), source_system="balance", mode="real", date_from=None, date_to=None, limit=1)]
    assert all(not response["ok"] for response in responses)
    assert all("secret" not in str(response) for response in responses)


@pytest.mark.parametrize("tenant", [None, "default", "t_beta"])
def test_connector_service_requires_authorized_context_before_factory(monkeypatch, tenant):
    factory = Mock(side_effect=AssertionError("connector must not open"))
    monkeypatch.setattr(history, "get_connector", factory)
    with db.authenticated_tenant_context(None if tenant is None else "t_alpha"):
        with pytest.raises(ValueError):
            history.import_posted_history_from_connector("balance", tenant_id=tenant)
    factory.assert_not_called()


def test_demo_factory_has_the_verified_tenant_and_rejects_invalid_modes():
    with db.authenticated_tenant_context("t_alpha"):
        connector = history.get_connector("balance", mode="demo", tenant_id="t_alpha")
        assert connector.tenant_id == "t_alpha"
        assert connector.history(tenant_id="t_alpha") == []
        with pytest.raises(ValueError):
            history.get_connector("balance", mode="demo", tenant_id="t_beta")
        with pytest.raises(ValueError, match="MODE_UNSUPPORTED"):
            history.get_connector("balance", mode="unknown", tenant_id="t_alpha")
        with pytest.raises(ValueError, match="SOURCE_UNSUPPORTED"):
            history.get_connector("unknown", mode="demo", tenant_id="t_alpha")
