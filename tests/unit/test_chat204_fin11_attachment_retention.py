"""FIN-11: preserve approved/correction attachments and evidence in Draft.

Regression-first isolated route tests. No actual GCS call, DB mutation,
production file deletion, ERP operation, or public migration.
"""
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api import routes_approval as route
from app.api.services import storage_service


def _code(result):
    if isinstance(result, dict):
        return (result.get("error") or {}).get("code")
    return (json.loads(result.body)["error"])["code"]


def _request():
    item = SimpleNamespace(
        filename="evidence.pdf",
        content_type="application/pdf",
        read=AsyncMock(return_value=b"%PDF-1.7 approved source evidence"),
    )
    return SimpleNamespace(
        state=SimpleNamespace(tenant_id="tenant-a"),
        form=AsyncMock(return_value={"file": item}),
    )


def _record(*, status="pending_approval", entry_type="normal",
            source=None, stored_path=None, stored_name=None):
    return {
        "id": 77, "status": status, "entry_type": entry_type,
        "reversal_of_draft_id": source, "attached_file_path": stored_path,
        "attached_file_name": stored_name, "attached_file_size": None,
    }


def _conn(row, *, updated=None):
    conn = AsyncMock()
    async def fetchrow(sql, *params):
        statement = " ".join(str(sql).lower().split())
        if statement.startswith("select"):
            assert "for update nowait" in statement
            assert "where id =" in statement and "tenant_id =" in statement
            assert params == (77, "tenant-a")
            return row
        assert statement.startswith("update journal_drafts")
        assert "returning id" in statement
        assert "reversal_of_draft_id is null" in statement
        assert "entry_type in (" in statement
        assert "status in (" in statement
        assert "attached_file_path is null" in statement
        return updated
    conn.fetchrow = AsyncMock(side_effect=fetchrow)
    conn.execute = AsyncMock(side_effect=AssertionError("unconditional write"))
    return conn


@asynccontextmanager
async def _scoped(conn):
    yield conn


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [
    _record(status="posted"),
    _record(status="approved"),
    _record(status="rejected"),
    _record(status="awaiting_cfo"),
    _record(status="pending_approval", entry_type="reversal", source=41),
    _record(status="pending_approval", entry_type="adjustment", source=41),
    _record(status="pending_approval", entry_type="normal", source=41),
    _record(status="pending_approval", entry_type=None),
    _record(status="pending_approval", stored_path="tenant-a/existing.pdf",
            stored_name="original.pdf"),
])
async def test_attachment_upload_never_changes_protected_or_existing_evidence(row):
    conn = _conn(row)
    req = _request()
    with patch.object(route, "require_permission"), \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn", lambda: _scoped(conn)), \
         patch.object(storage_service, "upload_file", return_value="tenant-a/new.pdf") as upload:
        result = await route.attach_file_to_draft(77, req)
    assert _code(result) in {
        "FIN11_ATTACHMENT_MUTATION_BLOCKED", "FIN11_ATTACHMENT_REPLACE_HOLD",
    }
    upload.assert_not_called()
    conn.execute.assert_not_awaited()
    assert conn.fetchrow.await_count == 1


@pytest.mark.asyncio
async def test_attachment_upload_requires_durable_blob_and_atomic_mutable_draft_update():
    conn = _conn(_record(), updated={"id": 77})
    req = _request()
    with patch.object(route, "require_permission"), \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn", lambda: _scoped(conn)), \
         patch.object(storage_service, "upload_file", return_value="tenant-a/new.pdf") as upload:
        result = await route.attach_file_to_draft(77, req)
    assert result["ok"] is True
    assert conn.fetchrow.await_count == 2
    conn.execute.assert_not_awaited()
    upload.assert_called_once()


@pytest.mark.asyncio
async def test_attachment_upload_does_not_claim_success_when_storage_failed():
    conn = _conn(_record(), updated={"id": 77})
    req = _request()
    with patch.object(route, "require_permission"), \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn", lambda: _scoped(conn)), \
         patch.object(storage_service, "upload_file", return_value=None):
        result = await route.attach_file_to_draft(77, req)
    assert _code(result) == "ATTACHMENT_STORAGE_UNAVAILABLE"
    assert conn.fetchrow.await_count == 1
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachment_delete_is_retention_hold_not_physical_gcs_delete():
    # No approved immutable evidence-retention/atomic unlink protocol exists.
    conn = _conn(_record(stored_path="tenant-a/evidence.pdf",
                         stored_name="evidence.pdf"))
    req = _request()
    with patch.object(route, "require_permission"), \
         patch.object(route, "resolve_tenant_id", return_value="tenant-a"), \
         patch.object(route, "get_conn", lambda: _scoped(conn)), \
         patch.object(storage_service, "delete_file") as remove:
        result = await route.delete_draft_attachment(77, req)
    assert _code(result) == "FIN11_ATTACHMENT_DELETE_HOLD"
    remove.assert_not_called()
    conn.execute.assert_not_awaited()
