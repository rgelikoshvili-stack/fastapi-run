"""tests/unit/test_sprint3c_cross_reference.py

Sprint 3C unit tests — Cross-reference service and AI tool.
No live DB.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.cross_reference_service import _payment_status


# ─────────────────────────────────────────────────────────────────────────────
# Payment status helper
# ─────────────────────────────────────────────────────────────────────────────

class TestPaymentStatus:
    def test_paid(self):
        assert _payment_status(1000.0, 1000.0) == "paid"

    def test_paid_within_1pct(self):
        assert _payment_status(1000.0, 995.0) == "paid"

    def test_partial(self):
        assert _payment_status(1000.0, 500.0) == "partial"

    def test_unpaid(self):
        assert _payment_status(1000.0, 0.0) == "unpaid"

    def test_unknown_no_total(self):
        assert _payment_status(None, 500.0) == "unknown"

    def test_unknown_zero_total(self):
        assert _payment_status(0.0, 0.0) == "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Service tests (mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

def _mock_conn(rows_map: dict | None = None):
    """Build a mock asyncpg connection that returns rows_map[table_key]."""
    rows_map = rows_map or {}
    call_count = [0]

    async def fake_fetch(query, *args):
        call_count[0] += 1
        key = call_count[0]
        return rows_map.get(key, [])

    async def fake_fetchrow(query, *args):
        call_count[0] += 1
        key = call_count[0]
        results = rows_map.get(key, [])
        return results[0] if results else None

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=fake_fetch)
    conn.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    return conn


def _make_row(**kwargs):
    row = MagicMock()
    row.__iter__ = lambda self: iter(kwargs.items())
    row.keys = lambda: kwargs.keys()

    def getitem(key):
        return kwargs.get(key)

    row.__getitem__ = MagicMock(side_effect=getitem)
    row.items = lambda: kwargs.items()
    # Make dict(row) work by defining __iter__ on keys
    return dict(kwargs)


@pytest.mark.asyncio
async def test_get_cross_ref_by_party_empty():
    from app.api.services.cross_reference_service import get_cross_ref_by_party

    conn = _mock_conn({})
    with patch("app.api.services.cross_reference_service.get_conn", return_value=conn):
        result = await get_cross_ref_by_party("tenant1", "Acme LLC")

    assert "waybills" in result
    assert "tax_invoices" in result
    assert "bank_transactions" in result
    assert "journal_drafts" in result
    assert result["query"] == "Acme LLC"
    assert result["summary"]["waybill_count"] == 0


@pytest.mark.asyncio
async def test_get_cross_ref_by_party_missing_query():
    from app.api.services.cross_reference_service import get_cross_ref_by_party

    result = await get_cross_ref_by_party("tenant1", "")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_cross_ref_by_party_inn_detection():
    from app.api.services.cross_reference_service import get_cross_ref_by_party

    conn = _mock_conn({})
    with patch("app.api.services.cross_reference_service.get_conn", return_value=conn):
        result = await get_cross_ref_by_party("tenant1", "123456789")

    assert result["party_type"] == "INN"


@pytest.mark.asyncio
async def test_get_cross_ref_by_party_name_detection():
    from app.api.services.cross_reference_service import get_cross_ref_by_party

    conn = _mock_conn({})
    with patch("app.api.services.cross_reference_service.get_conn", return_value=conn):
        result = await get_cross_ref_by_party("tenant1", "Acme LLC")

    assert result["party_type"] == "name"


@pytest.mark.asyncio
async def test_get_cross_ref_by_document_not_found():
    from app.api.services.cross_reference_service import get_cross_ref_by_document

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.cross_reference_service.get_conn", return_value=conn):
        result = await get_cross_ref_by_document("tenant1", "WB-NOTFOUND")

    assert result["found"] is False


@pytest.mark.asyncio
async def test_get_cross_ref_by_document_missing_number():
    from app.api.services.cross_reference_service import get_cross_ref_by_document

    result = await get_cross_ref_by_document("tenant1", "")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_cross_ref_by_document_waybill_found():
    from app.api.services.cross_reference_service import get_cross_ref_by_document

    wb_row = {
        "id": 1, "waybill_number": "WB-001", "waybill_date": None,
        "seller_inn": "111", "seller_name": "Seller LLC",
        "buyer_inn": "222", "buyer_name": "Buyer LLC",
        "total_amount": 1180.0, "vat_amount": 180.0,
        "status": "imported", "source": "rsge_import",
    }

    conn = AsyncMock()
    # fetchrow calls: 1=waybill, 2=triangle, then more
    fetchrow_results = [wb_row, None, None]
    fetchrow_idx = [0]

    async def fake_fetchrow(*args):
        i = fetchrow_idx[0]
        fetchrow_idx[0] += 1
        return fetchrow_results[i] if i < len(fetchrow_results) else None

    conn.fetchrow = AsyncMock(side_effect=fake_fetchrow)
    conn.fetch = AsyncMock(return_value=[])
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.cross_reference_service.get_conn", return_value=conn):
        result = await get_cross_ref_by_document("tenant1", "WB-001")

    assert result["found"] is True
    assert result["anchor_type"] == "waybill"
    assert result["invoiced_amount"] == 1180.0


# ─────────────────────────────────────────────────────────────────────────────
# Route tests
# ─────────────────────────────────────────────────────────────────────────────

def _make_request(tenant_id="t1"):
    req = MagicMock()
    req.state.tenant_id = tenant_id
    req.state.role = "accountant"
    req.state.authenticated = True
    return req


@pytest.mark.asyncio
async def test_party_route_success():
    from app.api.routes_cross_reference import cross_reference_by_party

    mock_result = {
        "query": "Acme LLC",
        "party_type": "name",
        "waybills": [],
        "tax_invoices": [],
        "bank_transactions": [],
        "journal_drafts": [],
        "summary": {
            "waybill_count": 0, "tax_invoice_count": 0,
            "bank_txn_count": 0, "draft_count": 0,
            "total_invoiced_gel": 0, "total_paid_gel": 0,
            "payment_status": "unknown", "unmatched_waybills": 0,
        },
    }

    with patch("app.api.routes_cross_reference.require_permission"), \
         patch("app.api.routes_cross_reference.resolve_tenant_id", return_value="t1"), \
         patch("app.api.routes_cross_reference.get_cross_ref_by_party",
               return_value=mock_result) as mock_fn:
        response = await cross_reference_by_party(
            request=_make_request(), q="Acme LLC", limit=20
        )

    assert response["ok"] is True
    mock_fn.assert_called_once_with("t1", "Acme LLC", limit=20)


@pytest.mark.asyncio
async def test_document_route_not_found():
    from app.api.routes_cross_reference import cross_reference_by_document

    with patch("app.api.routes_cross_reference.require_permission"), \
         patch("app.api.routes_cross_reference.resolve_tenant_id", return_value="t1"), \
         patch("app.api.routes_cross_reference.get_cross_ref_by_document",
               return_value={"found": False, "doc_number": "WB-XXX"}):
        response = await cross_reference_by_document(
            request=_make_request(), number="WB-XXX"
        )

    assert response["ok"] is False
    assert response["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_document_route_found():
    from app.api.routes_cross_reference import cross_reference_by_document

    mock_result = {
        "found": True,
        "anchor_type": "waybill",
        "anchor_doc_number": "WB-001",
        "anchor": {"id": 1, "waybill_number": "WB-001", "total_amount": 1180.0},
        "triangle_match": None,
        "linked_tax_invoice": None,
        "bank_payments": [],
        "journal_drafts": [],
        "payment_status": "unpaid",
        "paid_amount": 0.0,
        "invoiced_amount": 1180.0,
    }

    with patch("app.api.routes_cross_reference.require_permission"), \
         patch("app.api.routes_cross_reference.resolve_tenant_id", return_value="t1"), \
         patch("app.api.routes_cross_reference.get_cross_ref_by_document",
               return_value=mock_result):
        response = await cross_reference_by_document(
            request=_make_request(), number="WB-001"
        )

    assert response["ok"] is True
    assert response["data"]["anchor_type"] == "waybill"


# ─────────────────────────────────────────────────────────────────────────────
# AI tool tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_document_chain_tool_by_party():
    from app.api.services.ai_tool_registry import run_tool

    mock_result = {
        "query": "Acme LLC",
        "party_type": "name",
        "waybills": [], "tax_invoices": [], "bank_transactions": [],
        "journal_drafts": [],
        "summary": {
            "waybill_count": 0, "tax_invoice_count": 0,
            "bank_txn_count": 0, "draft_count": 0,
            "total_invoiced_gel": 0.0, "total_paid_gel": 0.0,
            "payment_status": "unknown", "unmatched_waybills": 0,
        },
    }

    # Patch at the service module, where _get_document_chain imports it lazily
    with patch("app.api.services.cross_reference_service.get_conn") as mock_get_conn:
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=False)
        mock_get_conn.return_value = mock_conn

        result = await run_tool("get_document_chain", {"query": "Acme LLC"}, "tenant1")

    assert result["approval_required"] is False
    assert "waybills" in result


@pytest.mark.asyncio
async def test_get_document_chain_tool_no_params():
    from app.api.services.ai_tool_registry import run_tool

    result = await run_tool("get_document_chain", {}, "tenant1")
    assert "error" in result


def test_get_document_chain_in_registry():
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS, _TOOL_MAP
    assert "get_document_chain" in TOOL_DESCRIPTIONS
    assert "get_document_chain" in _TOOL_MAP


def test_router_prefix():
    from app.api.routes_cross_reference import router
    assert router.prefix == "/cross-reference"


def test_routes_registered():
    from app.api.routes_cross_reference import router
    paths = [r.path for r in router.routes]
    assert "/cross-reference/party" in paths
    assert "/cross-reference/document" in paths
