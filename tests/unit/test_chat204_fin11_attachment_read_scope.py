"""FIN-11 evidence attachment reads need RBAC and tenant-bound storage provenance.

Regression-first unit tests. All GCS calls and database connections mocked.
"""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.api import routes_approval as route
from app.api.services import storage_service


def _request():
    return SimpleNamespace(state=SimpleNamespace(tenant_id="tenant-a"))


def _code(result):
    if isinstance(result, dict):
        return (result.get("error") or {}).get("code")
    return json.loads(result.body)["error"]["code"]


@asynccontextmanager
async def _conn(row):
    class FakeConn:
        fetchrow = AsyncMock(return_value=row)
    conn = FakeConn()
    yield conn


@pytest.mark.asyncio
async def test_attachment_read_requires_approval_read_before_db_or_storage():
    req = _request()
    with patch.object(route, "require_permission",
                      side_effect=PermissionError("approval:read required")) as gate, \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn",
                      side_effect=AssertionError("unauthorized database lookup")) as db, \
         patch.object(storage_service, "generate_signed_url") as signed, \
         patch.object(storage_service, "download_file") as download:
        with pytest.raises(PermissionError, match="approval:read required"):
            await route.get_draft_attachment(77, req)
    gate.assert_called_once_with(req, "approval:read")
    db.assert_not_called()
    signed.assert_not_called()
    download.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [
    "tenant-b/2026-11-01/secret.pdf",
    "tenant-a/../tenant-b/secret.pdf",
    "../tenant-a/secret.pdf",
])
async def test_attachment_read_holds_stored_wrong_tenant_or_ambiguous_key(path):
    req = _request()
    row = {
        "attached_file_path": path,
        "attached_file_name": "secret.pdf", "attached_file_size": 6,
    }
    with patch.object(route, "require_permission") as gate, \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn", lambda: _conn(row)), \
         patch.object(storage_service, "generate_signed_url", return_value="https://wrong.example/secret") as signed, \
         patch.object(storage_service, "download_file") as download:
        result = await route.get_draft_attachment(77, req)
    assert _code(result) == "FIN11_ATTACHMENT_STORAGE_TENANT_HOLD"
    gate.assert_called_once_with(req, "approval:read")
    signed.assert_not_called()
    download.assert_not_called()


@pytest.mark.asyncio
async def test_authorized_attested_attachment_path_keeps_existing_envelope():
    req = _request()
    row = {
        "attached_file_path": "tenant-a/2026-11-01/valid.pdf",
        "attached_file_name": "valid.pdf", "attached_file_size": 42,
    }
    with patch.object(route, "require_permission") as gate, \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn", lambda: _conn(row)), \
         patch.object(storage_service, "generate_signed_url", return_value="https://signed.example/file") as signed:
        result = await route.get_draft_attachment(77, req)
    assert result["ok"] is True
    assert result["data"]["file_name"] == "valid.pdf"
    assert result["data"]["signed_url"] == "https://signed.example/file"
    gate.assert_called_once_with(req, "approval:read")
    signed.assert_called_once()
