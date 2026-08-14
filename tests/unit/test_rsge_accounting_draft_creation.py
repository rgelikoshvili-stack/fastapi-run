"""tests/unit/test_rsge_accounting_draft_creation.py — Accounting draft from RS.ge docs."""
import asyncio
import inspect
from unittest.mock import AsyncMock, MagicMock


def _make_doc(direction="incoming", buyer_inn="B", seller_inn="A",
              draft_id=None, evidence_id=None):
    return {
        "id": 10, "tenant_id": "t1", "rsge_id": "999",
        "reg_no": "INV-001", "doc_type": "invoice",
        "seller_inn": seller_inn, "seller_name": "Seller",
        "buyer_inn": buyer_inn, "buyer_name": "Buyer",
        "doc_date": "2026-01-15", "amount": 1180.0, "vat_amount": 180.0,
        "currency": "GEL", "rsge_status": "1", "rsge_status_code": "1",
        "direction": direction, "draft_id": draft_id, "evidence_id": evidence_id,
    }


# ── 1. Incoming purchase draft ────────────────────────────────────────────────

def test_incoming_doc_creates_purchase_draft():
    from app.api.services.rsge_document_service import create_draft_from_document

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[
        _make_doc(direction="incoming"),  # SELECT
        {"id": 55},                       # INSERT journal_drafts
    ])
    mock_conn.execute = AsyncMock()

    result = asyncio.run(
        create_draft_from_document(mock_conn, "t1", 10, own_inn="B")
    )
    assert result["draft_id"] == 55
    assert result["created"] is True
    assert result["draft_type"] == "purchase"
    assert result["direction"] == "incoming"
    assert result["debit_account"] == "1310"
    assert result["credit_account"] == "3110"


# ── 2. Outgoing sales draft ───────────────────────────────────────────────────

def test_outgoing_doc_creates_sales_draft():
    from app.api.services.rsge_document_service import create_draft_from_document

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[
        _make_doc(direction="outgoing", seller_inn="ME", buyer_inn="THEM"),
        {"id": 66},
    ])
    mock_conn.execute = AsyncMock()

    result = asyncio.run(
        create_draft_from_document(mock_conn, "t1", 10, own_inn="ME")
    )
    assert result["draft_type"] == "sale"
    assert result["direction"] == "outgoing"
    assert result["debit_account"] == "1210"
    assert result["credit_account"] == "6110"


# ── 3. Unknown direction routes to review ────────────────────────────────────

def test_unknown_direction_routes_to_review():
    from app.api.services.rsge_document_service import create_draft_from_document

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[
        _make_doc(direction="unknown"),
        {"id": 77},
    ])
    mock_conn.execute = AsyncMock()

    result = asyncio.run(
        create_draft_from_document(mock_conn, "t1", 10, own_inn="")
    )
    # own_inn="" → company_identity_missing or unknown_requires_review
    assert result["draft_type"] in ("review_required", "company_identity_missing",
                                    "unknown_requires_review")


# ── 4. Draft creation is idempotent ──────────────────────────────────────────

def test_draft_creation_is_idempotent_when_draft_exists():
    from app.api.services.rsge_document_service import create_draft_from_document

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=_make_doc(draft_id=99))

    result = asyncio.run(
        create_draft_from_document(mock_conn, "t1", 10)
    )
    assert result["draft_id"] == 99
    assert result["created"] is False
    assert result["duplicate"] is True


# ── 5. Draft status is "drafted" (not auto-approved) ─────────────────────────

def test_draft_status_is_drafted():
    from app.api.services import rsge_document_service as svc
    src = inspect.getsource(svc.create_draft_from_document)
    assert "'drafted'" in src or '"drafted"' in src
    # Must NOT auto-approve or auto-post
    assert "approved" not in src.split("'drafted'")[0]
    assert "auto_approve" not in src


# ── 6. No autonomous posting ──────────────────────────────────────────────────

def test_draft_service_does_not_call_posting():
    from app.api.services import rsge_document_service as svc
    src = inspect.getsource(svc.create_draft_from_document)
    assert "posting_service" not in src
    assert "apply_draft" not in src
    assert "post_to_ledger" not in src


# ── 7. Amount calculation: net = amount - vat ────────────────────────────────

def test_draft_amount_is_net():
    from app.api.services.rsge_document_service import create_draft_from_document

    mock_conn = AsyncMock()
    doc = _make_doc(direction="incoming")
    doc["amount"] = 1180.0
    doc["vat_amount"] = 180.0
    mock_conn.fetchrow = AsyncMock(side_effect=[doc, {"id": 1}])
    mock_conn.execute = AsyncMock()

    result = asyncio.run(
        create_draft_from_document(mock_conn, "t1", 10, own_inn="B")
    )
    assert result["amount"] == 1000.0
    assert result["vat"] == 180.0
