"""tests/unit/test_rsge_evidence_creation.py — Evidence creation from RS.ge documents."""
import asyncio
import inspect
import json
from unittest.mock import AsyncMock, MagicMock


# ── 1. create_evidence_from_document inserts into documents table ─────────────

def test_evidence_created_from_rsge_document():
    from app.api.services.rsge_document_service import create_evidence_from_document

    mock_conn = AsyncMock()
    # First call: fetch document row
    doc_row = {
        "id": 10, "tenant_id": "t1", "rsge_id": "999",
        "reg_no": "INV-001", "doc_type": "invoice",
        "seller_inn": "A", "seller_name": "Seller Co",
        "buyer_inn": "B", "buyer_name": "Buyer Co",
        "doc_date": "2026-01-15", "amount": 3600.0, "vat_amount": 600.0,
        "currency": "GEL", "rsge_status": "1", "rsge_status_code": "1",
        "direction": "incoming", "evidence_id": None,
    }
    mock_conn.fetchrow = AsyncMock(side_effect=[
        dict(doc_row),         # SELECT rsge_documents
        {"id": 77},            # INSERT INTO documents
    ])
    mock_conn.execute = AsyncMock()

    result = asyncio.run(
        create_evidence_from_document(mock_conn, "t1", 10, actor="user1")
    )
    assert result["evidence_id"] == 77
    assert result["created"] is True
    assert result["duplicate"] is False


def test_evidence_creation_is_idempotent():
    from app.api.services.rsge_document_service import create_evidence_from_document

    mock_conn = AsyncMock()
    # Document already has evidence_id
    mock_conn.fetchrow = AsyncMock(return_value={
        "id": 10, "tenant_id": "t1", "rsge_id": "999",
        "reg_no": "X", "doc_type": "invoice", "doc_date": None,
        "amount": 100.0, "vat_amount": 18.0, "currency": "GEL",
        "seller_inn": "", "seller_name": "", "buyer_inn": "", "buyer_name": "",
        "rsge_status": "1", "rsge_status_code": "1",
        "direction": "incoming", "evidence_id": 42,  # already set
    })

    result = asyncio.run(
        create_evidence_from_document(mock_conn, "t1", 10)
    )
    assert result["evidence_id"] == 42
    assert result["created"] is False
    assert result["duplicate"] is True


def test_evidence_raises_for_missing_document():
    from app.api.services.rsge_document_service import create_evidence_from_document
    import pytest

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(
            create_evidence_from_document(mock_conn, "t1", 999)
        )


# ── 2. Evidence inserts correct document_type ─────────────────────────────────

def test_evidence_service_inserts_with_source_rsge():
    from app.api.services import rsge_document_service as svc
    src = inspect.getsource(svc.create_evidence_from_document)
    assert '"rs.ge"' in src or "'rs.ge'" in src
    assert "source" in src


# ── 3. Evidence from waybill ──────────────────────────────────────────────────

def test_waybill_evidence_created():
    from app.api.services.rsge_waybill_service import create_evidence_from_waybill

    mock_conn = AsyncMock()
    wb_row = {
        "id": 5, "tenant_id": "t1", "rsge_id": "WB1",
        "waybill_number": "WB-001", "full_amount": 500.0,
        "buyer_name": "Buyer", "buyer_tin": "111",
        "rsge_status": "1", "car_number": "AA-111",
        "begin_date": "2026-01-01", "evidence_id": None,
    }
    mock_conn.fetchrow = AsyncMock(side_effect=[dict(wb_row), {"id": 88}])
    mock_conn.execute = AsyncMock()

    result = asyncio.run(
        create_evidence_from_waybill(mock_conn, "t1", 5, actor="user1")
    )
    assert result["evidence_id"] == 88
    assert result["created"] is True


def test_waybill_evidence_is_idempotent():
    from app.api.services.rsge_waybill_service import create_evidence_from_waybill

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value={
        "id": 5, "tenant_id": "t1", "rsge_id": "WB1",
        "waybill_number": "WB-001", "full_amount": 100,
        "buyer_name": "B", "buyer_tin": "X", "rsge_status": "1",
        "car_number": "", "begin_date": None, "evidence_id": 66,
    })

    result = asyncio.run(
        create_evidence_from_waybill(mock_conn, "t1", 5)
    )
    assert result["evidence_id"] == 66
    assert result["duplicate"] is True
