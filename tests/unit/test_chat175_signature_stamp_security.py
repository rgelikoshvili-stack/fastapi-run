"""Chat175: signed-tenant RBAC and passive raster image security.

Uses synthetic Request scopes and mocked DB connections only.
Never sends production traffic or touches Cloud SQL, Cloud Run or local originals.
"""
import base64
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import routes_auth
from app.api.authz import require_signed_tenant_permission
from app.api.db import authenticated_tenant_context


_ONE_PIXEL_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8"
    "AAwMCAO+hU2cAAAAASUVORK5CYII="
)
_PNG_URL = "data:image/png;base64," + _ONE_PIXEL_PNG


def req(tenant="t_alpha", *, signed="t_alpha", role="admin", authenticated=True):
    r = Request({
        "type": "http", "method": "POST", "path": "/auth/signature",
        "raw_path": b"/auth/signature",
        "scheme": "http", "headers": [(b"x-tenant-id", b"t_beta")],
        "query_string": b"", "client": ("127.0.0.1", 17405),
        "server": ("127.0.0.1", 8080), "http_version": "1.1",
    })
    r.state.authenticated = authenticated
    r.state.role = role
    r.state.tenant_id = tenant
    r.state.auth_tenant_id = signed
    return r


def mocked_db(monkeypatch, *, update_result="UPDATE 1", saved=None):
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=update_result)
    conn.fetchrow = AsyncMock(return_value={"signature_b64": saved, "stamp_b64": saved})

    @asynccontextmanager
    async def db_context():
        yield conn

    monkeypatch.setattr(routes_auth, "get_conn", db_context)
    return conn


def test_png_and_legacy_clear_are_accepted_as_image_values():
    assert routes_auth._validated_identity_image(_PNG_URL) == _PNG_URL
    assert routes_auth._validated_identity_image("  " + _PNG_URL + "  ") == _PNG_URL
    assert routes_auth._validated_identity_image("") == ""
    assert routes_auth._validated_identity_image("  ") == ""


@pytest.mark.parametrize("value", [
    "javascript:alert(1)", "https://attacker.test/track.png",
    "<img src=x onerror=alert(1)>",
    'data:image/svg+xml;base64,' + base64.b64encode(b"<svg/>").decode(),
    "data:text/html;base64,PGh0bWw+",
    'data:image/png;base64," onerror="alert(1)',
    "data:image/png;base64,<unsafe>",
    "data:image/png;base64,AA==",  # PNG MIME, wrong magic
    "data:image/png;base64,??",
    "data:image/jpeg;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n123").decode(),
    "data:image/webp;base64," + base64.b64encode(b"RIFF" + b"\x00" * 20).decode(),
    "data:image/png;base64," + "A" * 2_000_001,
])
def test_non_image_or_active_content_rejected(value):
    with pytest.raises(ValueError):
        routes_auth._validated_identity_image(value)


@pytest.mark.parametrize("tenant,signed,role,authenticated,code", [
    ("t_alpha", "t_alpha", "viewer", True, 403),
    ("t_alpha", "t_alpha", "admin", False, 401),
    ("t_alpha", None, "admin", True, 403),
    ("t_beta", "t_alpha", "admin", True, 403),
    ("default", "default", "admin", True, 403),
    ("t_alpha", "t_alpha ", "admin", True, 403),
])
def test_sensitive_endpoints_deny_missing_or_spoofed_tenant_auth(
    tenant, signed, role, authenticated, code
):
    with authenticated_tenant_context(None):
        with pytest.raises(HTTPException) as exc:
            require_signed_tenant_permission(
                req(tenant, signed=signed, role=role, authenticated=authenticated),
                "settings:write",
            )
    assert exc.value.status_code == code


def test_matching_signed_tenant_requires_actual_db_context():
    r = req()
    with pytest.raises(HTTPException) as err:
        require_signed_tenant_permission(r, "settings:write")
    assert err.value.status_code == 403
    with authenticated_tenant_context("t_alpha"):
        assert require_signed_tenant_permission(r, "settings:write") == "t_alpha"
    with authenticated_tenant_context("t_beta"):
        with pytest.raises(HTTPException) as mismatch:
            require_signed_tenant_permission(r, "settings:write")
    assert mismatch.value.status_code == 403


@pytest.mark.asyncio
async def test_signature_and_stamp_save_only_signed_tenant(monkeypatch):
    conn = mocked_db(monkeypatch)
    with authenticated_tenant_context("t_alpha"):
        saved_signature = await routes_auth.save_signature(
            routes_auth.SignatureRequest(signature_b64=_PNG_URL),
            req(),
        )
        saved_stamp = await routes_auth.save_stamp(
            routes_auth.StampRequest(stamp_b64=_PNG_URL),
            req(),
        )
    assert saved_signature["ok"] is True
    assert saved_stamp["ok"] is True
    assert conn.execute.await_count == 2
    for call in conn.execute.await_args_list:
        assert call.args[-1] == "t_alpha"
        assert "WHERE tenant_id=" in call.args[0]


@pytest.mark.asyncio
async def test_signature_and_stamp_read_use_signed_tenant(monkeypatch):
    conn = mocked_db(monkeypatch, saved=_PNG_URL)
    with authenticated_tenant_context("t_alpha"):
        signature = await routes_auth.get_signature(req())
        stamp = await routes_auth.get_stamp(req())
    assert signature["data"]["signature_b64"] == _PNG_URL
    assert stamp["data"]["stamp_b64"] == _PNG_URL
    assert conn.fetchrow.await_count == 2
    assert all(call.args[-1] == "t_alpha" for call in conn.fetchrow.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize("field,route", [
    ("signature_b64", "save_signature"), ("stamp_b64", "save_stamp"),
])
async def test_malicious_data_rejected_without_any_db_write(monkeypatch, field, route):
    conn = mocked_db(monkeypatch)
    bad = 'data:image/svg+xml;base64,' + base64.b64encode(b"<svg/>").decode()
    model = routes_auth.SignatureRequest if field == "signature_b64" else routes_auth.StampRequest
    with authenticated_tenant_context("t_alpha"):
        result = await getattr(routes_auth, route)(model(**{field: bad}), req())
    assert result.status_code == 422
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_tenant_update_not_falsely_reported_success(monkeypatch):
    mocked_db(monkeypatch, update_result="UPDATE 0")
    with authenticated_tenant_context("t_alpha"):
        result = await routes_auth.save_signature(
            routes_auth.SignatureRequest(signature_b64=_PNG_URL), req()
        )
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_empty_image_clears_signature_and_stamp(monkeypatch):
    conn = mocked_db(monkeypatch)
    with authenticated_tenant_context("t_alpha"):
        sig = await routes_auth.save_signature(
            routes_auth.SignatureRequest(signature_b64=""), req()
        )
        stamp = await routes_auth.save_stamp(
            routes_auth.StampRequest(stamp_b64=""), req()
        )
    assert sig["ok"] is True and stamp["ok"] is True
    assert all(call.args[1] == "" for call in conn.execute.await_args_list)


def test_frontend_legacy_stored_data_cannot_enter_html_attribute():
    html = Path("static/outgoing_form.html").read_text(encoding="utf8")
    assert "function _safeIdentityDataURL(value)" in html
    assert html.count("image.src=safe") == 2
    assert 'src="' + "$" + '{b64}"' not in html
    assert "image/svg+xml" not in html[html.index("function _safeIdentityDataURL"):html.index("function onSigDrop")]
