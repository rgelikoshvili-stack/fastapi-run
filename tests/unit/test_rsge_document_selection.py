"""tests/unit/test_rsge_document_selection.py — Document selection and sync tests."""
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock


# ── 1. sync-selected route exists ────────────────────────────────────────────

def test_sync_selected_route_exists():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    assert "sync-selected" in src or "sync_selected" in src
    assert "/documents" in src


# ── 2. Route requires authentication ─────────────────────────────────────────

def test_sync_route_requires_permission():
    import app.api.routes_rs_ge as m
    src = inspect.getsource(m)
    # posting:write is required for sync
    posting_write_count = src.count("posting:write")
    assert posting_write_count >= 3, "Expected multiple posting:write permission checks"


# ── 3. Sync does NOT auto-post ───────────────────────────────────────────────

def test_sync_selected_does_not_auto_post():
    from app.api.services import rsge_document_service as svc
    src = inspect.getsource(svc.sync_selected)
    # Must not call any posting functions
    assert "apply" not in src
    assert "post_to_ledger" not in src
    assert "posting_service" not in src


# ── 4. Multiple documents can be selected ─────────────────────────────────────

def test_sync_selected_handles_multiple_ids():
    from app.api.services.rsge_document_service import sync_selected

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 1})

    mock_connector = MagicMock()
    mock_connector.get_user_invoices.return_value = [
        {"ID": str(i), "SELLER_TIN": "A", "BUYER_TIN": "B",
         "INVOICE_NUMBER": f"N{i}", "TOTAL": 100*i, "VAT": 18*i, "STATUS": "1"}
        for i in range(1, 6)
    ]

    result = asyncio.run(
        sync_selected(mock_conn, "tenant1", ["1", "2", "3"], mock_connector)
    )
    assert result["synced_count"] == 3
    assert result["total_requested"] == 3


# ── 5. Deduplication: re-sync does not create duplicates ─────────────────────

def test_sync_selected_is_idempotent():
    from app.api.services import rsge_document_service as svc
    src = inspect.getsource(svc._upsert_document)
    # Must use ON CONFLICT / UPSERT
    assert "ON CONFLICT" in src or "on conflict" in src.lower()
    assert "DO UPDATE" in src or "do update" in src.lower()


# ── 6. SyncSelectedRequest model has rsge_ids field ──────────────────────────

def test_sync_request_model_structure():
    import app.api.routes_rs_ge as m
    # SyncSelectedRequest must be defined
    assert hasattr(m, "SyncSelectedRequest")
    model = m.SyncSelectedRequest
    fields = model.model_fields
    assert "rsge_ids" in fields
