import importlib
import os
from pathlib import Path


os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("DATABASE_URL", "")


def _registered_routes():
    from main import app

    return [
        (tuple(sorted(route.methods)), route.path)
        for route in app.routes
        if hasattr(route, "methods")
    ]


def test_app_imports_with_invoice_and_waybill_routes():
    importlib.import_module("main")
    importlib.import_module("app.core.router_registry")
    importlib.import_module("app.api.domain.documents")
    importlib.import_module("app.api.routes_invoice")
    importlib.import_module("app.api.routes_invoices")
    importlib.import_module("app.api.routes_waybills")


def test_no_duplicate_route_path_method_collision():
    seen = {}
    for methods, path in _registered_routes():
        key = (methods, path)
        seen[key] = seen.get(key, 0) + 1

    duplicates = [key for key, count in seen.items() if count > 1]
    assert duplicates == []


def test_legacy_invoice_parse_route_still_registered_or_shimmed():
    routes = _registered_routes()
    assert (("POST",), "/invoice/parse") in routes

    legacy = importlib.import_module("app.api.routes_invoice")
    assert legacy.router.prefix == "/invoice"


def test_invoices_routes_still_registered():
    paths = [path for _methods, path in _registered_routes()]
    assert any(path.startswith("/invoices") for path in paths)


def test_waybill_routes_registered_once():
    routes = _registered_routes()
    assert routes.count((("GET",), "/waybills/stats")) == 1
    assert routes.count((("GET",), "/waybills/list")) == 1
    assert routes.count((("POST",), "/waybills/create")) == 1


def test_waybill_routes_do_not_call_posting_apply():
    src = Path("app/api/routes_waybills.py").read_text(encoding="utf-8")
    forbidden = (
        "posting/apply",
        "apply_posting_service",
        "post_draft_to",
        "mock_posting",
        "journal_drafts SET status = 'posted'",
    )
    assert [token for token in forbidden if token in src] == []


def test_no_balance_activation_in_invoice_waybill_routes():
    files = [
        Path("app/api/routes_invoice.py"),
        Path("app/api/routes_invoices.py"),
        Path("app/api/routes_waybills.py"),
        Path("app/core/router_registry.py"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    forbidden = (
        "BALANCE_API_KEY=",
        "BalanceConnector",
        "connector.activate",
        "connector_activate",
        "gcloud run services update",
    )
    assert [token for token in forbidden if token in combined] == []
