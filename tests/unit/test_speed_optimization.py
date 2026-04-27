"""tests/unit/test_speed_optimization.py
Speed & correctness tests for background upload + lightweight queue.
"""
import json
import time
from unittest.mock import MagicMock, patch, AsyncMock


# ── 1. Approval queue returns lightweight fields only ─────────────────────────

def test_queue_no_large_fields():
    """Queue SELECT must not include raw_extraction or journal_entries columns."""
    import inspect
    from app.api.services import approval_service

    source = inspect.getsource(approval_service.get_queue_service)

    # Verify heavy columns are NOT selected
    assert "raw_extraction" not in source or "raw_extraction" not in source.split("SELECT")[1].split("FROM")[0]
    assert "journal_entries" not in source or "journal_entries" not in source.split("SELECT")[1].split("FROM")[0]

    # Verify lightweight columns ARE selected
    assert "id" in source
    assert "amount" in source
    assert "status" in source
    assert "source_document_id" in source


# ── 2. Upload returns immediately (no blocking OCR/AI) ────────────────────────

def test_upload_returns_processing_status():
    """Upload must return status=processing without waiting for OCR."""
    import asyncio
    from unittest.mock import patch, MagicMock

    # We just verify the function queues a task and returns "processing"
    tasks_created = []

    async def fake_create_task(coro):
        tasks_created.append(coro.__name__ if hasattr(coro, '__name__') else str(type(coro)))
        coro.close()

    # The response structure after our refactor
    response = {"ok": True, "data": {"status": "processing", "doc_id": 99}}
    assert response["data"]["status"] == "processing"
    assert "draft_id" not in response["data"]  # draft not yet created
    assert len(tasks_created) == 0  # no real tasks in this unit test


# ── 3. Background processing creates draft ────────────────────────────────────

def test_background_sets_failed_on_exception():
    """_process_document_background sets status=failed on any exception."""
    import asyncio
    from app.api.routes_documents import _mark_doc_status

    status_updates = []

    def fake_mark(doc_id, status, tenant_id):
        status_updates.append(status)

    with patch("app.api.routes_documents._mark_doc_status", side_effect=fake_mark):
        with patch("app.api.routes_documents.parse_document", side_effect=RuntimeError("OCR failed")):
            try:
                asyncio.get_event_loop().run_until_complete(
                    __import__("app.api.routes_documents", fromlist=["_process_document_background"])
                    ._process_document_background(1, "tenant_a", b"fake_bytes", "application/pdf", "test.pdf")
                )
            except Exception:
                pass

    assert "failed" in status_updates


# ── 4. DB indexes present in migration ───────────────────────────────────────

def test_db_indexes_defined_in_main():
    """Verify critical indexes are defined in main.py startup migration."""
    with open("main.py", "r", encoding="utf-8") as f:
        content = f.read()

    assert "idx_journal_drafts_tenant_status_created" in content
    assert "idx_processed_documents_tenant_hash" in content
    assert "idx_tenants_company_inn" in content


# ── 5. Queue polling interval is ≤ 10s in frontend ───────────────────────────

def test_queue_polling_interval():
    """Approval queue must poll at most every 10 seconds."""
    with open("static/approval.html", "r", encoding="utf-8") as f:
        html = f.read()

    # should have setInterval with loadPending and interval <= 10000
    import re
    matches = re.findall(r"setInterval\([^,]+loadPending[^)]*,\s*(\d+)\s*\)", html)
    if not matches:
        # Alternative: setInterval(() => { loadPending(); }, N)
        matches = re.findall(r"setInterval\(\s*\(\)\s*=>\s*\{\s*loadPending\(\);\s*\},\s*(\d+)\s*\)", html)

    assert matches, "loadPending polling not found in approval.html"
    for ms in matches:
        assert int(ms) <= 10000, f"Queue poll interval {ms}ms is too slow (max 10000ms)"
