"""Recovery tests for email documents saved before AI processing completes."""
from __future__ import annotations

from contextlib import asynccontextmanager
from email.message import EmailMessage
from unittest.mock import AsyncMock, patch

import pytest


class _EmailDocumentDB:
    def __init__(self, status=None, draft_id=None):
        self.row = None if status is None else {"id": 41, "status": status, "draft_id": draft_id}
        self.saved = False

    async def fetchrow(self, query, *args):
        if "SELECT id, status, draft_id FROM email_documents" in query:
            return self.row
        if "INSERT INTO email_documents" in query:
            self.saved = True
            self.row = {"id": 41, "status": "pending", "draft_id": None}
            return {"id": 41}
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetchval(self, query, *args):
        assert "engine_metadata->>'source_doc_id'" in query
        return None

    async def execute(self, query, *args):
        if "UPDATE email_documents SET status='pending'" in query:
            assert self.row["status"] != "processed"
        elif "UPDATE email_documents SET draft_id" in query:
            self.row.update(draft_id=args[0], status=args[1])
        else:
            raise AssertionError(f"Unexpected execute query: {query}")


def _message():
    msg = EmailMessage()
    msg.set_content("invoice attached")
    msg.add_attachment(b"fake pdf bytes", maintype="application", subtype="pdf", filename="invoice.pdf")
    return msg.as_bytes()


def _patch_collector(monkeypatch, db, ai):
    from app.api.services import email_collector as ec

    @asynccontextmanager
    async def fake_conn():
        yield db

    monkeypatch.setattr(ec, "get_conn", fake_conn)
    monkeypatch.setattr(ec, "get_tenant_email_credentials", AsyncMock(return_value={"email": "local-test", "app_password": "not-used"}))
    monkeypatch.setattr(ec, "_imap_connect", lambda *_: object())
    monkeypatch.setattr(ec, "_imap_search_unseen", lambda *_: [b"1"])
    monkeypatch.setattr(ec, "_imap_fetch_raw", lambda *_: _message())
    monkeypatch.setattr(ec, "_imap_mark_seen", lambda *_: None)
    monkeypatch.setattr(ec, "_imap_logout", lambda *_: None)
    monkeypatch.setattr(ec, "_extract_text_from_pdf", lambda *_: "A sufficiently long invoice document for AI processing")
    from app.api.services import ai_processor
    monkeypatch.setattr(ai_processor, "ai_process_document", ai)
    return ec


@pytest.mark.asyncio
async def test_timeout_after_save_before_ai_then_rerun_resumes_pending(monkeypatch):
    db = _EmailDocumentDB()
    ai = AsyncMock(side_effect=[asyncio_cancelled(), {"ok": True, "draft_id": 77}])
    ec = _patch_collector(monkeypatch, db, ai)

    with pytest.raises(__import__("asyncio").CancelledError):
        await ec.collect_tenant_inbox("tenant-a")
    assert db.saved
    assert db.row["status"] == "pending"

    result = await ec.collect_tenant_inbox("tenant-a")
    assert result["processed"] == 1
    assert ai.await_count == 2
    assert db.row == {"id": 41, "status": "processed", "draft_id": 77}


def asyncio_cancelled():
    import asyncio
    return asyncio.CancelledError()


@pytest.mark.asyncio
async def test_pending_duplicate_is_retried_not_skipped(monkeypatch):
    db = _EmailDocumentDB(status="pending")
    ai = AsyncMock(return_value={"ok": True, "draft_id": 77})
    ec = _patch_collector(monkeypatch, db, ai)

    result = await ec.collect_tenant_inbox("tenant-a")

    assert result["processed"] == 1
    ai.assert_awaited_once()
    assert db.row["status"] == "processed"


@pytest.mark.asyncio
async def test_processed_document_is_skipped(monkeypatch):
    db = _EmailDocumentDB(status="processed", draft_id=77)
    ai = AsyncMock()
    ec = _patch_collector(monkeypatch, db, ai)

    result = await ec.collect_tenant_inbox("tenant-a")

    assert result["processed"] == 0
    ai.assert_not_awaited()


@pytest.mark.asyncio
async def test_existing_ai_draft_completes_pending_document_without_duplicate_ai(monkeypatch):
    db = _EmailDocumentDB(status="processing")
    ai = AsyncMock()
    ec = _patch_collector(monkeypatch, db, ai)

    with patch.object(ec, "_existing_email_draft", new=AsyncMock(return_value=88)):
        result = await ec.collect_tenant_inbox("tenant-a")

    assert result["processed"] == 1
    assert result["drafts"][0]["draft_id"] == 88
    ai.assert_not_awaited()
    assert db.row["status"] == "processed"
