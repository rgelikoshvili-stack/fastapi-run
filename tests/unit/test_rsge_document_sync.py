"""tests/unit/test_rsge_document_sync.py — RS.ge document sync unit tests."""
import asyncio
import inspect
import json
from unittest.mock import AsyncMock, MagicMock, patch

from app.api.services.rsge_document_service import _map_invoice_to_dto, RsgeDocumentDTO


# ── 1. DTO mapping ───────────────────────────────────────────────────────────

def test_map_invoice_to_dto_maps_seller_buyer():
    raw = {
        "ID": "999",
        "INVOICE_NUMBER": "INV-001",
        "SELLER_TIN": "200000000",
        "SELLER_NAME": "ს.ს. გამყიდველი",
        "BUYER_TIN": "100000000",
        "BUYER_NAME": "შ.პ.ს. მყიდველი",
        "OPERATION_DATE": "2026-01-15",
        "TOTAL": "3600.00",
        "VAT": "600.00",
        "STATUS": "1",
    }
    dto = _map_invoice_to_dto(raw, own_inn="100000000")
    assert dto.rsge_id == "999"
    assert dto.reg_no == "INV-001"
    assert dto.seller_inn == "200000000"
    assert dto.buyer_inn == "100000000"
    assert dto.amount == 3600.0
    assert dto.vat_amount == 600.0
    assert dto.direction == "incoming"
    assert dto.doc_type == "invoice"


def test_map_invoice_to_dto_outgoing():
    raw = {"ID": "1", "SELLER_TIN": "123", "BUYER_TIN": "456",
           "TOTAL": 1000, "VAT": 150, "STATUS": "2"}
    dto = _map_invoice_to_dto(raw, own_inn="123")
    assert dto.direction == "outgoing"


def test_map_invoice_to_dto_unknown_direction():
    raw = {"ID": "2", "SELLER_TIN": "111", "BUYER_TIN": "222", "TOTAL": 500, "VAT": 0}
    dto = _map_invoice_to_dto(raw, own_inn="")
    assert dto.direction == "unknown"


def test_source_hash_is_stable():
    raw = {"ID": "5", "INVOICE_NUMBER": "X", "TOTAL": 100, "VAT": 18, "STATUS": "1"}
    dto = _map_invoice_to_dto(raw)
    h1 = dto.source_hash()
    h2 = dto.source_hash()
    assert h1 == h2
    assert len(h1) == 32


# ── 2. list_documents merges local status ─────────────────────────────────────

def test_list_documents_includes_sync_status():
    from app.api.services.rsge_document_service import list_documents

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[
        {"rsge_id": "10", "id": 42, "evidence_id": 7, "draft_id": None, "synced_at": "2026-01-01"}
    ])

    mock_connector = MagicMock()
    mock_connector.get_user_invoices.return_value = [
        {"ID": "10", "SELLER_TIN": "111", "BUYER_TIN": "222",
         "INVOICE_NUMBER": "X", "TOTAL": 500, "VAT": 0, "STATUS": "1"}
    ]

    result = asyncio.run(
        list_documents(mock_conn, "tenant1", mock_connector)
    )
    assert len(result) == 1
    assert result[0]["id"] == "10"
    assert result[0]["synced"] is True
    assert result[0]["evidence_id"] == 7
    assert result[0]["source"] == "rs.ge"


# ── 3. sync_selected upserts documents ───────────────────────────────────────

def test_sync_selected_returns_summary():
    from app.api.services.rsge_document_service import sync_selected

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={"id": 55})

    mock_connector = MagicMock()
    mock_connector.get_user_invoices.return_value = [
        {"ID": "10", "INVOICE_NUMBER": "N1", "SELLER_TIN": "A", "BUYER_TIN": "B",
         "TOTAL": 1000, "VAT": 150, "STATUS": "0"}
    ]

    result = asyncio.run(
        sync_selected(mock_conn, "tenant1", ["10"], mock_connector)
    )
    assert result["synced_count"] == 1
    assert result["error_count"] == 0
    assert result["synced"][0]["rsge_id"] == "10"


def test_sync_selected_reports_not_found():
    from app.api.services.rsge_document_service import sync_selected

    mock_conn = AsyncMock()
    mock_connector = MagicMock()
    mock_connector.get_user_invoices.return_value = []  # empty

    result = asyncio.run(
        sync_selected(mock_conn, "tenant1", ["999"], mock_connector)
    )
    assert result["error_count"] == 1
    assert "not found" in result["errors"][0]["error"]


# ── 4. Service exists and is structured correctly ─────────────────────────────

def test_document_service_has_required_functions():
    from app.api.services import rsge_document_service as m
    assert hasattr(m, "list_documents")
    assert hasattr(m, "sync_selected")
    assert hasattr(m, "create_evidence_from_document")
    assert hasattr(m, "create_draft_from_document")


def test_document_service_has_tenant_id_in_all_upserts():
    from app.api.services import rsge_document_service as m
    src = inspect.getsource(m._upsert_document)
    assert "tenant_id" in src
