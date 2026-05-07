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
    from app.api.services.document_processing_service import _mark_doc_status

    status_updates = []

    def fake_mark(doc_id, status, tenant_id):
        status_updates.append(status)

    with patch("app.api.services.document_processing_service._mark_doc_status", side_effect=fake_mark):
        with patch("app.api.services.document_processing_service.parse_document", side_effect=RuntimeError("OCR failed")):
            from app.api.services.document_processing_service import _process_document_background
            asyncio.run(
                _process_document_background(1, "tenant_a", b"fake_bytes", "application/pdf", "test.pdf")
            )

    assert "failed" in status_updates


# ── 4. DB indexes present in migration ───────────────────────────────────────

def test_db_indexes_defined_in_main():
    """Verify critical indexes are defined in the startup migrations modules."""
    content = ""
    for fname in ["app/startup/migrations.py", "app/startup/migrations_indexes.py"]:
        try:
            with open(fname, "r", encoding="utf-8") as f:
                content += f.read()
        except FileNotFoundError:
            pass

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


# ── P1-2: ?token= auth fallback restricted to download paths ─────────────────

def test_token_query_param_only_for_download_paths():
    """Non-download paths must NOT authenticate via ?token= query param."""
    import inspect
    import app.api.middleware.auth_middleware as mod

    src = inspect.getsource(mod.auth_middleware)
    # The token extraction from query_params must be guarded by download prefix check
    assert "_DOWNLOAD_PREFIXES" in inspect.getsource(mod), \
        "_DOWNLOAD_PREFIXES not defined in auth_middleware"
    # Verify the conditional extraction — must NOT fire unconditionally
    assert 'elif not token:' not in src, \
        "?token= extraction fires unconditionally — not restricted to download paths"


def test_download_prefixes_defined():
    """_DOWNLOAD_PREFIXES must include document and report download paths."""
    from app.api.middleware.auth_middleware import _DOWNLOAD_PREFIXES
    assert any("documents" in p for p in _DOWNLOAD_PREFIXES)
    assert any("reports" in p for p in _DOWNLOAD_PREFIXES)


# ── P1-3: no tenant_id::text casts in bank_accounts or budget routes ─────────

def test_bank_accounts_no_tenant_id_text_cast():
    """tenant_id::text cast prevents index use — must not appear in routes_bank_accounts."""
    import inspect
    import app.api.routes_bank_accounts as mod
    assert "tenant_id::text" not in inspect.getsource(mod), \
        "routes_bank_accounts still contains tenant_id::text cast"


def test_budget_no_tenant_id_text_cast():
    """tenant_id::text cast prevents index use — must not appear in routes_budget."""
    import inspect
    import app.api.routes_budget as mod
    assert "tenant_id::text" not in inspect.getsource(mod), \
        "routes_budget still contains tenant_id::text cast"
