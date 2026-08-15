"""tests/unit/test_sprint3a_rsge_import.py

Sprint 3A unit tests — RS.ge document import.
No live DB, no live RS.ge connection.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.rsge_document_parser import (
    parse_rsge_waybills,
    parse_rsge_tax_invoices,
)

# ─────────────────────────────────────────────────────────────────────────────
# Parser unit tests (pure, no DB)
# ─────────────────────────────────────────────────────────────────────────────

WAYBILL_XML = """<?xml version="1.0" encoding="utf-8"?>
<Waybills>
  <Waybill>
    <Number>WB-2026-001</Number>
    <CreateDate>2026-08-01</CreateDate>
    <Seller><Tin>123456789</Tin><Name>Test Seller LLC</Name></Seller>
    <Buyer><Tin>987654321</Tin><Name>Test Buyer LLC</Name></Buyer>
    <TransportationStartAddress>Tbilisi</TransportationStartAddress>
    <TransportationEndAddress>Batumi</TransportationEndAddress>
    <Car><Number>AA-123-BB</Number></Car>
    <Driver><Name>Vaso Vasadze</Name></Driver>
    <Goods>
      <Good>
        <Name>Product 1</Name>
        <Quantity>10</Quantity>
        <UnitOfMeasure>pcs</UnitOfMeasure>
        <Price>100</Price>
        <Total>1000</Total>
      </Good>
    </Goods>
    <GoodsTotalPrice>1000.00</GoodsTotalPrice>
    <VATAmount>180.00</VATAmount>
    <TotalAmount>1180.00</TotalAmount>
  </Waybill>
</Waybills>
""".encode("utf-8")

TAX_INVOICE_XML = """<?xml version="1.0" encoding="utf-8"?>
<Invoices>
  <Invoice>
    <SerialNumber>AA</SerialNumber>
    <Number>000001</Number>
    <CreateDate>2026-08-02</CreateDate>
    <Seller><Tin>123456789</Tin><Name>Test Seller LLC</Name></Seller>
    <Buyer><Tin>987654321</Tin><Name>Test Buyer LLC</Name></Buyer>
    <Items>
      <Item>
        <Name>Product 1</Name>
        <Quantity>10</Quantity>
        <Price>100</Price>
        <Total>1000</Total>
        <VAT>180</VAT>
      </Item>
    </Items>
    <TotalWithoutVAT>1000.00</TotalWithoutVAT>
    <VATTotal>180.00</VATTotal>
    <TotalWithVAT>1180.00</TotalWithVAT>
    <WaybillNumber>WB-2026-001</WaybillNumber>
  </Invoice>
</Invoices>
""".encode("utf-8")

WAYBILL_JSON = json.dumps([{
    "waybill_number": "WB-2026-002",
    "waybill_date": "2026-08-03",
    "seller_inn": "111222333",
    "seller_name": "JSON Seller LLC",
    "buyer_inn": "444555666",
    "buyer_name": "JSON Buyer LLC",
    "subtotal": "2000.00",
    "vat_amount": "360.00",
    "total_amount": "2360.00",
}]).encode()

TAX_INVOICE_JSON = json.dumps([{
    "invoice_number": "BB000002",
    "invoice_series": "BB",
    "invoice_date": "2026-08-04",
    "seller_inn": "111222333",
    "seller_name": "JSON Seller LLC",
    "buyer_inn": "444555666",
    "buyer_name": "JSON Buyer LLC",
    "subtotal": "2000.00",
    "vat_amount": "360.00",
    "total_amount": "2360.00",
    "related_waybill_number": "WB-2026-002",
}]).encode()


class TestWaybillXmlParser:
    def test_parses_waybill_list(self):
        result = parse_rsge_waybills(WAYBILL_XML)
        assert len(result) == 1
        wb = result[0]
        assert wb["waybill_number"] == "WB-2026-001"
        assert wb["waybill_date"] == "2026-08-01"
        assert wb["seller_inn"] == "123456789"
        assert wb["seller_name"] == "Test Seller LLC"
        assert wb["buyer_inn"] == "987654321"
        assert wb["buyer_name"] == "Test Buyer LLC"
        assert wb["transport_from"] == "Tbilisi"
        assert wb["transport_to"] == "Batumi"
        assert wb["vehicle_number"] == "AA-123-BB"
        assert wb["driver_name"] == "Vaso Vasadze"

    def test_parses_amounts(self):
        result = parse_rsge_waybills(WAYBILL_XML)
        wb = result[0]
        from decimal import Decimal
        assert wb["subtotal"] == Decimal("1000.00")
        assert wb["vat_amount"] == Decimal("180.00")
        assert wb["total_amount"] == Decimal("1180.00")

    def test_parses_line_items(self):
        result = parse_rsge_waybills(WAYBILL_XML)
        items = result[0]["line_items"]
        assert len(items) == 1
        assert items[0]["name"] == "Product 1"
        assert items[0]["quantity"] == "10"

    def test_returns_empty_for_garbage(self):
        result = parse_rsge_waybills(b"not xml or json at all!!!")
        assert result == []

    def test_returns_empty_for_empty_bytes(self):
        result = parse_rsge_waybills(b"")
        # empty string may fail XML parse — should not raise
        assert isinstance(result, list)

    def test_single_waybill_element_as_root(self):
        xml = b"""<Waybill>
            <Number>WB-SINGLE</Number>
            <CreateDate>2026-08-01</CreateDate>
            <Seller><Tin>111</Tin><Name>S</Name></Seller>
            <Buyer><Tin>222</Tin><Name>B</Name></Buyer>
            <TotalAmount>500.00</TotalAmount>
        </Waybill>"""
        result = parse_rsge_waybills(xml)
        assert len(result) == 1
        assert result[0]["waybill_number"] == "WB-SINGLE"


class TestTaxInvoiceXmlParser:
    def test_parses_invoice_list(self):
        result = parse_rsge_tax_invoices(TAX_INVOICE_XML)
        assert len(result) == 1
        inv = result[0]
        assert inv["invoice_number"] == "AA000001"
        assert inv["invoice_series"] == "AA"
        assert inv["invoice_date"] == "2026-08-02"
        assert inv["seller_inn"] == "123456789"
        assert inv["buyer_inn"] == "987654321"

    def test_parses_amounts(self):
        result = parse_rsge_tax_invoices(TAX_INVOICE_XML)
        inv = result[0]
        from decimal import Decimal
        assert inv["subtotal"] == Decimal("1000.00")
        assert inv["vat_amount"] == Decimal("180.00")
        assert inv["total_amount"] == Decimal("1180.00")

    def test_related_waybill_number(self):
        result = parse_rsge_tax_invoices(TAX_INVOICE_XML)
        assert result[0]["related_waybill_number"] == "WB-2026-001"

    def test_returns_empty_for_garbage(self):
        result = parse_rsge_tax_invoices(b"garbage")
        assert result == []


class TestJsonParsers:
    def test_waybill_json(self):
        result = parse_rsge_waybills(WAYBILL_JSON)
        assert len(result) == 1
        assert result[0]["waybill_number"] == "WB-2026-002"
        assert result[0]["seller_inn"] == "111222333"

    def test_tax_invoice_json(self):
        result = parse_rsge_tax_invoices(TAX_INVOICE_JSON)
        assert len(result) == 1
        assert result[0]["invoice_number"] == "BB000002"
        assert result[0]["related_waybill_number"] == "WB-2026-002"

    def test_json_amounts_decimal(self):
        result = parse_rsge_waybills(WAYBILL_JSON)
        from decimal import Decimal
        assert result[0]["total_amount"] == Decimal("2360.00")

    def test_single_json_object(self):
        single = json.dumps({
            "waybill_number": "WB-SOLO",
            "total_amount": "100.00",
        }).encode()
        result = parse_rsge_waybills(single)
        assert len(result) == 1
        assert result[0]["waybill_number"] == "WB-SOLO"

    def test_invalid_json(self):
        result = parse_rsge_waybills(b"{broken json")
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# Route endpoint tests (mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

def _make_request(tenant_id="test-tenant", role="accountant", user_id="u1"):
    req = MagicMock()
    req.state.tenant_id = tenant_id
    req.state.role = role
    req.state.user_id = user_id
    req.state.authenticated = True
    return req


def _make_upload(content: bytes, filename="test.xml"):
    upload = AsyncMock()
    upload.read = AsyncMock(return_value=content)
    upload.filename = filename
    return upload


def _get_handler(fn):
    """Unwrap slowapi limiter decorator to get the raw async function."""
    return getattr(fn, "__wrapped__", fn)


@pytest.mark.asyncio
async def test_import_waybill_success():
    import app.api.routes_rsge_documents as mod
    handler = _get_handler(mod.import_rsge_waybill)

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, k: 42 if k == "id" else None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[None, mock_row])
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(file=_make_upload(WAYBILL_XML), request=_make_request())

    assert response["ok"] is True
    assert response["data"]["inserted"] == 1
    assert response["data"]["skipped"] == 0


@pytest.mark.asyncio
async def test_import_waybill_duplicate_skipped():
    import app.api.routes_rsge_documents as mod
    handler = _get_handler(mod.import_rsge_waybill)

    existing_row = MagicMock()
    existing_row.__getitem__ = lambda self, k: 99

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=existing_row)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(file=_make_upload(WAYBILL_XML), request=_make_request())

    assert response["ok"] is True
    assert response["data"]["inserted"] == 0
    assert response["data"]["skipped"] == 1


@pytest.mark.asyncio
async def test_import_waybill_empty_file():
    import app.api.routes_rsge_documents as mod
    from fastapi.responses import JSONResponse
    handler = _get_handler(mod.import_rsge_waybill)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"):
        response = await handler(file=_make_upload(b""), request=_make_request())

    # http_error returns a JSONResponse directly (status 400)
    assert isinstance(response, JSONResponse)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_import_waybill_parse_error():
    import app.api.routes_rsge_documents as mod
    handler = _get_handler(mod.import_rsge_waybill)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"):
        response = await handler(file=_make_upload(b"not xml"), request=_make_request())

    assert response["ok"] is False
    assert response["error"]["code"] == "PARSE_ERROR"


@pytest.mark.asyncio
async def test_import_tax_invoice_success():
    import app.api.routes_rsge_documents as mod
    handler = _get_handler(mod.import_rsge_tax_invoice)

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, k: 55 if k == "id" else None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[None, None, mock_row])
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(file=_make_upload(TAX_INVOICE_XML), request=_make_request())

    assert response["ok"] is True
    assert response["data"]["inserted"] == 1


@pytest.mark.asyncio
async def test_import_tax_invoice_json():
    import app.api.routes_rsge_documents as mod
    handler = _get_handler(mod.import_rsge_tax_invoice)

    mock_row = MagicMock()
    mock_row.__getitem__ = lambda self, k: 56 if k == "id" else None

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(side_effect=[None, None, mock_row])
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(
            file=_make_upload(TAX_INVOICE_JSON, "invoices.json"),
            request=_make_request(),
        )

    assert response["ok"] is True
    assert response["data"]["inserted"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# AI tool unit test
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_rsge_documents_tool():
    from app.api.services.ai_tool_registry import run_tool

    mock_conn = AsyncMock()
    mock_conn.fetch = AsyncMock(return_value=[])
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch("app.api.services.ai_tool_registry.get_conn", return_value=mock_conn):
        result = await run_tool("get_rsge_documents", {"doc_type": "both"}, "tenant1")

    assert "waybills" in result
    assert "tax_invoices" in result
    assert result["approval_required"] is False


@pytest.mark.asyncio
async def test_get_rsge_documents_tool_registered():
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS, _TOOL_MAP
    assert "get_rsge_documents" in TOOL_DESCRIPTIONS
    assert "get_rsge_documents" in _TOOL_MAP


def test_tool_names_consistent():
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS, _TOOL_MAP, TOOL_NAMES
    assert set(TOOL_NAMES) == set(TOOL_DESCRIPTIONS.keys())
    assert set(_TOOL_MAP.keys()) == set(TOOL_DESCRIPTIONS.keys())
