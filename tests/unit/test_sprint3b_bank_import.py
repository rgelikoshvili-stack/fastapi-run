"""tests/unit/test_sprint3b_bank_import.py

Sprint 3B unit tests — Bank statement import (TBC/BOG/generic).
No live DB, no network.
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.services.bank_format_detector import (
    detect_bank,
    get_col_map,
    extract_partner_from_description,
    TBC_COL_MAP,
    BOG_COL_MAP,
    GENERIC_COL_MAP,
)

# ─────────────────────────────────────────────────────────────────────────────
# Bank format detector tests
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectBank:
    def test_tbc_in_filename(self):
        assert detect_bank("tbc_statement_2026.csv", b"some,data") == "TBC"

    def test_bog_in_filename(self):
        assert detect_bank("bog_statement_2026.xlsx", b"some,data") == "BOG"

    def test_tbc_content_marker(self):
        content = b"TBCBank Statement Export\nDate,Details,Debit,Credit"
        assert detect_bank("statement.csv", content) == "TBC"

    def test_bog_content_marker(self):
        content = b"Bank of Georgia\nStatement\nDate,Description,Amount"
        assert detect_bank("statement.csv", content) == "BOG"

    def test_mygemini_is_tbc(self):
        content = b'<root xmlns:g="http://www.mygemini.com/schemas/mygemini">'
        assert detect_bank("export.xml", content) == "TBC"

    def test_unknown_returns_unknown(self):
        content = b"Date,Amount,Description\n2026-08-01,100,Test"
        assert detect_bank("statement.csv", content) == "UNKNOWN"

    def test_tbc_georgian_headers(self):
        content = "ოპ. თარიღი,დეტალები".encode("utf-8")
        assert detect_bank("export.xlsx", content) == "TBC"

    def test_filename_takes_priority_over_content(self):
        # filename says TBC, content says BOG
        content = b"Bank of Georgia statement"
        assert detect_bank("tbc_export.csv", content) == "TBC"

    def test_case_insensitive_filename(self):
        assert detect_bank("TBC_Statement.CSV", b"") == "TBC"
        assert detect_bank("BOG_Statement.XLSX", b"") == "BOG"


class TestGetColMap:
    def test_tbc_returns_tbc_map(self):
        m = get_col_map("TBC")
        assert m is TBC_COL_MAP

    def test_bog_returns_bog_map(self):
        m = get_col_map("BOG")
        assert m is BOG_COL_MAP

    def test_unknown_returns_generic(self):
        m = get_col_map("UNKNOWN")
        assert m is GENERIC_COL_MAP

    def test_all_maps_have_required_fields(self):
        required = {"date", "description", "paid_out", "paid_in", "balance", "currency"}
        for name, col_map in [("TBC", TBC_COL_MAP), ("BOG", BOG_COL_MAP), ("GENERIC", GENERIC_COL_MAP)]:
            for field in required:
                assert field in col_map, f"{name} col_map missing '{field}'"


class TestExtractPartner:
    def test_transfer_to_pattern(self):
        result = extract_partner_from_description("Transfer to: Acme Ltd, ref 123")
        assert result is not None
        assert "Acme" in result

    def test_payment_to_pattern(self):
        result = extract_partner_from_description("payment to Supplier Corp for services")
        assert result is not None

    def test_none_description(self):
        assert extract_partner_from_description(None) is None

    def test_empty_description(self):
        assert extract_partner_from_description("") is None

    def test_no_pattern_match(self):
        result = extract_partner_from_description("random bank description text")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Parser tests
# ─────────────────────────────────────────────────────────────────────────────

TBC_CSV = b"date,details,debit,credit,balance,reference no,currency\n2026-08-01,Payment to supplier,1000.00,,49000.00,TBC123,GEL\n2026-08-02,Receipt from client,,5000.00,54000.00,TBC124,GEL\n"

GENERIC_CSV = b"Date,Description,Amount,Currency\n2026-08-01,Test payment,-1000.00,GEL\n2026-08-02,Test receipt,500.00,USD\n"


class TestCsvParsing:
    def test_parse_tbc_csv_basic(self):
        from app.api.routes_bank_statements import _parse_csv
        col_map = get_col_map("TBC")
        rows = _parse_csv(TBC_CSV, col_map)
        assert len(rows) == 2

    def test_tbc_csv_amounts(self):
        from app.api.routes_bank_statements import _parse_csv
        col_map = get_col_map("TBC")
        rows = _parse_csv(TBC_CSV, col_map)
        # First row: debit 1000 → amount = -1000
        assert rows[0]["amount"] == -1000.0
        # Second row: credit 5000 → amount = +5000
        assert rows[1]["amount"] == 5000.0

    def test_tbc_csv_transaction_ref(self):
        from app.api.routes_bank_statements import _parse_csv
        col_map = get_col_map("TBC")
        rows = _parse_csv(TBC_CSV, col_map)
        assert rows[0]["transaction_ref"] == "TBC123"
        assert rows[1]["transaction_ref"] == "TBC124"

    def test_tbc_csv_currency(self):
        from app.api.routes_bank_statements import _parse_csv
        col_map = get_col_map("TBC")
        rows = _parse_csv(TBC_CSV, col_map)
        assert rows[0]["currency"] == "GEL"

    def test_generic_csv_negative_amount(self):
        from app.api.routes_bank_statements import _parse_csv
        col_map = get_col_map("UNKNOWN")
        rows = _parse_csv(GENERIC_CSV, col_map)
        assert len(rows) == 2
        # Negative amount → paid_out
        assert rows[0]["amount"] == -1000.0

    def test_generic_csv_positive_amount(self):
        from app.api.routes_bank_statements import _parse_csv
        col_map = get_col_map("UNKNOWN")
        rows = _parse_csv(GENERIC_CSV, col_map)
        assert rows[1]["amount"] == 500.0

    def test_empty_csv_returns_empty(self):
        from app.api.routes_bank_statements import _parse_csv
        rows = _parse_csv(b"", get_col_map("UNKNOWN"))
        assert rows == []

    def test_header_only_csv(self):
        from app.api.routes_bank_statements import _parse_csv
        rows = _parse_csv(b"date,description,amount\n", get_col_map("UNKNOWN"))
        assert rows == []


TBC_XML = b"""<?xml version="1.0"?>
<Statement xmlns:g="http://www.mygemini.com/schemas/mygemini">
  <g:Record>
    <g:Date>2026-08-01</g:Date>
    <g:Description>Payment to vendor</g:Description>
    <g:PartnerName>Vendor LLC</g:PartnerName>
    <g:PaidOut>2000.00</g:PaidOut>
    <g:PaidIn>0</g:PaidIn>
    <g:Balance>48000.00</g:Balance>
    <g:OperationCode>2</g:OperationCode>
    <g:TransactionId>XML001</g:TransactionId>
    <g:Currency>GEL</g:Currency>
  </g:Record>
</Statement>
"""


class TestXmlParsing:
    def test_parse_tbc_xml(self):
        from app.api.routes_bank_statements import _parse_xml
        rows = _parse_xml(TBC_XML)
        assert len(rows) == 1

    def test_xml_amount_is_negative(self):
        from app.api.routes_bank_statements import _parse_xml
        rows = _parse_xml(TBC_XML)
        assert rows[0]["amount"] == -2000.0

    def test_xml_partner_name(self):
        from app.api.routes_bank_statements import _parse_xml
        rows = _parse_xml(TBC_XML)
        assert rows[0]["partner"] == "Vendor LLC"

    def test_xml_transaction_ref(self):
        from app.api.routes_bank_statements import _parse_xml
        rows = _parse_xml(TBC_XML)
        assert rows[0]["transaction_ref"] == "XML001"

    def test_invalid_xml_returns_empty(self):
        from app.api.routes_bank_statements import _parse_xml
        rows = _parse_xml(b"not xml")
        assert rows == []


# ─────────────────────────────────────────────────────────────────────────────
# Route handler tests (mocked DB)
# ─────────────────────────────────────────────────────────────────────────────

def _make_request(tenant_id="t1", role="accountant"):
    req = MagicMock()
    req.state.tenant_id = tenant_id
    req.state.role = role
    req.state.authenticated = True
    return req


def _make_upload(content: bytes, filename="statement.csv"):
    f = AsyncMock()
    f.read = AsyncMock(return_value=content)
    f.filename = filename
    return f


def _get_handler(fn):
    return getattr(fn, "__wrapped__", fn)


@pytest.mark.asyncio
async def test_import_bank_statement_success():
    import app.api.routes_bank_statements as mod
    handler = _get_handler(mod.import_bank_statement)

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)  # no duplicates
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(
            request=_make_request(),
            file=_make_upload(TBC_CSV, "tbc_statement.csv"),
            bank="",
            account_number="",
        )

    assert response["ok"] is True
    assert response["data"]["inserted"] == 2
    assert response["data"]["bank"] == "TBC"
    assert response["data"]["detected_from"] == "auto"


@pytest.mark.asyncio
async def test_import_bank_statement_explicit_bank():
    import app.api.routes_bank_statements as mod
    handler = _get_handler(mod.import_bank_statement)

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(
            request=_make_request(),
            file=_make_upload(TBC_CSV, "statement.csv"),
            bank="BOG",
            account_number="",
        )

    assert response["ok"] is True
    assert response["data"]["bank"] == "BOG"
    assert response["data"]["detected_from"] == "provided"


@pytest.mark.asyncio
async def test_import_bank_statement_dedup():
    import app.api.routes_bank_statements as mod
    handler = _get_handler(mod.import_bank_statement)

    existing = MagicMock()
    existing.__getitem__ = lambda s, k: "existing-id"

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=existing)  # all rows are duplicates
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(
            request=_make_request(),
            file=_make_upload(TBC_CSV, "tbc_statement.csv"),
            bank="",
            account_number="",
        )

    assert response["ok"] is True
    assert response["data"]["inserted"] == 0
    assert response["data"]["skipped"] == 2


@pytest.mark.asyncio
async def test_import_empty_file():
    import app.api.routes_bank_statements as mod
    from fastapi.responses import JSONResponse
    handler = _get_handler(mod.import_bank_statement)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"):
        response = await handler(
            request=_make_request(),
            file=_make_upload(b"", "empty.csv"),
            bank="",
            account_number="",
        )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_import_xml_format():
    import app.api.routes_bank_statements as mod
    handler = _get_handler(mod.import_bank_statement)

    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    with patch.object(mod, "require_permission"), \
         patch.object(mod, "resolve_tenant_id", return_value="t1"), \
         patch.object(mod, "get_conn", return_value=mock_conn):
        response = await handler(
            request=_make_request(),
            file=_make_upload(TBC_XML, "tbc_export.xml"),
            bank="",
            account_number="",
        )

    assert response["ok"] is True
    assert response["data"]["inserted"] == 1


def test_router_prefix():
    from app.api.routes_bank_statements import router
    assert router.prefix == "/bank-statements"


def test_import_endpoint_registered():
    from app.api.routes_bank_statements import router
    paths = [r.path for r in router.routes]
    assert "/bank-statements/import" in paths
    assert "/bank-statements/batches" in paths
    assert "/bank-statements/transactions" in paths
