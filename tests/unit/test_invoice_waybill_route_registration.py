"""Route registration and tenant/RBAC behavior for invoice and waybill APIs."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET", "pr91-test-secret-minimum-32-bytes-long")
os.environ.setdefault("TEST_MODE", "1")
os.environ.setdefault("DATABASE_URL", "")

from main import app


def _token(role="admin", tenant_id="tenant_a", *, include_tenant=True):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "pr91-test-user",
        "type": "access",
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=15)).timestamp()),
    }
    if include_tenant:
        payload["tenant_id"] = tenant_id
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")


def _client(role="admin", tenant_id="tenant_a", *, include_tenant=True):
    headers = {"Authorization": f"Bearer {_token(role, tenant_id, include_tenant=include_tenant)}"}
    return TestClient(app, headers=headers)


def _registered_routes():
    """Flatten both classic APIRoutes and newer lazy FastAPI included routers."""
    found = []

    def visit(routes, prefix=""):
        for route in routes:
            include_context = getattr(route, "include_context", None)
            original_router = getattr(route, "original_router", None)
            if include_context is not None and original_router is not None:
                child_prefix = f"{prefix}/{include_context.prefix.strip('/')}".rstrip("/")
                visit(original_router.routes, child_prefix)
                continue

            path = getattr(route, "path", None)
            methods = getattr(route, "methods", None)
            if path is not None and methods:
                full_path = f"{prefix}/{path.strip('/')}".rstrip("/") or "/"
                found.extend((method, full_path) for method in methods if method not in {"HEAD", "OPTIONS"})
                continue

            nested = getattr(route, "routes", None)
            if nested is not None:
                visit(nested, prefix)

    visit(app.routes)
    return found


def test_invoice_and_waybill_routes_registered_exactly_once():
    routes = _registered_routes()
    expected = {
        ("POST", "/invoice/parse"),
        ("POST", "/invoices/create"),
        ("GET", "/invoices/list"),
        ("GET", "/invoices/{invoice_id}"),
        ("GET", "/waybills/stats"),
        ("GET", "/waybills/list"),
        ("POST", "/waybills/create"),
        ("GET", "/waybills/{waybill_id}"),
        ("POST", "/waybills/{waybill_id}/status"),
    }
    for route in expected:
        assert routes.count(route) == 1, f"expected exactly one registration for {route}"


def test_waybill_goods_route_is_separate_from_integer_detail_route():
    routes = _registered_routes()
    assert ("GET", "/rs-ge/waybills/goods-by-number") in routes
    assert ("GET", "/waybills/goods-by-number") not in routes
    assert routes.count(("GET", "/waybills/{waybill_id}")) == 1


def test_invoice_static_and_dynamic_paths_do_not_collide():
    routes = _registered_routes()
    assert routes.count(("GET", "/invoices/list")) == 1
    assert routes.count(("GET", "/invoices/{invoice_id}")) == 1
    assert routes.count(("POST", "/invoices/create")) == 1


def test_invoice_parse_and_waybill_paths_are_in_openapi():
    paths = app.openapi()["paths"]
    assert "post" in paths["/invoice/parse"]
    assert "get" in paths["/invoices/{invoice_id}"]
    assert "get" in paths["/waybills/{waybill_id}"]


def test_waybill_create_requires_authentication():
    response = TestClient(app).post("/waybills/create", json={"waybill_number": "WB-A"})
    assert response.status_code == 401


def test_waybill_create_requires_write_permission():
    response = _client(role="viewer").post("/waybills/create", json={"waybill_number": "WB-A"})
    assert response.status_code == 403


def test_waybill_status_update_requires_authentication():
    response = TestClient(app).post("/waybills/17/status", json={"status": "matched"})
    assert response.status_code == 401


def test_waybill_status_update_requires_write_permission():
    response = _client(role="viewer").post("/waybills/17/status", json={"status": "matched"})
    assert response.status_code == 403


class _WaybillDB:
    def __init__(self):
        self.create_args = None
        self.read_args = None
        self.update_args = None

    async def fetchval(self, _query, *args):
        self.create_args = args
        return 17

    async def fetchrow(self, _query, *args):
        self.read_args = args
        waybill_id, tenant_id = args
        if waybill_id == 17 and tenant_id == "tenant_b":
            return {"id": 17, "tenant_id": tenant_id, "waybill_number": "WB-B"}
        return None

    async def execute(self, _query, *args):
        self.update_args = args
        return "UPDATE 1" if args[2] == "tenant_b" else "UPDATE 0"


def _mock_waybill_db(monkeypatch):
    from app.api import routes_waybills

    db = _WaybillDB()

    @asynccontextmanager
    async def fake_get_conn():
        yield db

    monkeypatch.setattr(routes_waybills, "get_conn", fake_get_conn)
    return db


def test_waybill_create_uses_authenticated_tenant_not_header(monkeypatch):
    db = _mock_waybill_db(monkeypatch)
    response = _client(tenant_id="tenant_a").post(
        "/waybills/create",
        headers={"X-Tenant-ID": "tenant_b"},
        json={"waybill_number": "WB-A"},
    )
    assert response.status_code == 200
    assert db.create_args[0] == "tenant_a"


def test_tenant_a_cannot_read_or_update_tenant_b_waybill(monkeypatch):
    db = _mock_waybill_db(monkeypatch)
    client = _client(tenant_id="tenant_a")

    read = client.get("/waybills/17", headers={"X-Tenant-ID": "tenant_b"})
    assert read.json()["error"]["code"] == "NOT_FOUND"
    assert db.read_args == (17, "tenant_a")

    update = client.post(
        "/waybills/17/status",
        headers={"X-Tenant-ID": "tenant_b"},
        json={"status": "matched"},
    )
    assert update.json()["error"]["code"] == "NOT_FOUND"
    assert db.update_args == ("matched", 17, "tenant_a")


@pytest.mark.parametrize(
    ("tenant_id", "include_tenant"),
    [(None, False), ("", True), (123, True)],
)
def test_missing_or_invalid_tenant_claim_fails_closed(tenant_id, include_tenant):
    response = _client(role="admin", tenant_id=tenant_id, include_tenant=include_tenant).post(
        "/waybills/create", json={"waybill_number": "WB-A"}
    )
    assert response.status_code == 403
    assert "tenant" in str(response.json()).lower()


def test_rsge_sync_is_default_deny_before_database_or_soap(monkeypatch):
    for name in (
        "RSGE_ENABLED",
        "RSGE_READ_ONLY",
        "RSGE_DRY_RUN",
        "RSGE_LIVE_ACTIONS_ENABLED",
        "RSGE_ALLOW_WAYBILL_ACTIONS",
        "RSGE_FINAL_APPROVAL_RECORDED",
    ):
        monkeypatch.delenv(name, raising=False)

    from app.api import routes_rs_ge

    async def forbidden_get_conn():
        raise AssertionError("database/SOAP phase must not be reached when the action gate denies")

    monkeypatch.setattr(routes_rs_ge, "get_conn", forbidden_get_conn)
    response = _client().post(
        "/rs-ge/sync",
        json={"mode": "v1", "operator_confirmed": True},
    )
    assert response.status_code == 403
    assert "safety gates" in response.text.lower()


def test_read_only_rsge_query_is_get_and_sync_is_explicit_post():
    paths = app.openapi()["paths"]
    assert "get" in paths["/rs-ge/waybills/goods-by-number"]
    assert "post" in paths["/rs-ge/sync"]
    assert "post" not in paths["/rs-ge/waybills/goods-by-number"]


def test_router_registration_has_no_automatic_rsge_sync_or_ddl():
    registry = Path("app/core/router_registry.py").read_text(encoding="utf-8")
    main_source = Path("main.py").read_text(encoding="utf-8")
    startup_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in Path("app/startup").glob("*.py")
    )
    assert "sync_waybills_from_rsge(" not in registry
    assert "rsge_waybill_soap" not in registry
    assert "sync_waybills_from_rsge(" not in main_source
    assert "run_rsge_migrations" not in main_source
    assert "sync_waybills_from_rsge(" not in startup_sources
    assert "rsge_waybill_soap" not in startup_sources
    assert "run_rsge_migrations" not in startup_sources
