"""tests/unit/test_rsge_document_detail_mapping.py — RS.ge document detail field mapping."""
import json


# ── Raw RS.ge invoice response fixture ───────────────────────────────────────

def _raw_invoice():
    return {
        "ID": "12345",
        "INVOICE_NUMBER": "INV-2025-001",
        "SELLER_TIN": "405176367",
        "SELLER_NAME": "სს გამყიდველი",
        "BUYER_TIN": "999888777",
        "BUYER_NAME": "შპს მყიდველი",
        "OPERATION_DATE": "2025-01-15",
        "TOTAL": 1180.0,
        "VAT": 180.0,
        "STATUS": "0",
        "STATUS_TXT": "saved",
        "OVERHEAD_NO": "WB001",
    }


def _map_to_dto(raw, own_inn=""):
    from app.api.services.rsge_document_service import _map_invoice_to_dto
    return _map_invoice_to_dto(raw, own_inn)


# ── 1. rsge_id maps from ID ───────────────────────────────────────────────────

def test_rsge_id_mapped():
    dto = _map_to_dto(_raw_invoice())
    assert dto.rsge_id == "12345"


# ── 2. reg_no maps from INVOICE_NUMBER ───────────────────────────────────────

def test_reg_no_mapped():
    dto = _map_to_dto(_raw_invoice())
    assert dto.reg_no == "INV-2025-001"


# ── 3. seller_inn maps correctly ────────────────────────────────────────────

def test_seller_inn_mapped():
    dto = _map_to_dto(_raw_invoice())
    assert dto.seller_inn == "405176367"


# ── 4. buyer_inn maps correctly ─────────────────────────────────────────────

def test_buyer_inn_mapped():
    dto = _map_to_dto(_raw_invoice())
    assert dto.buyer_inn == "999888777"


# ── 5. amount maps from TOTAL ────────────────────────────────────────────────

def test_amount_mapped():
    dto = _map_to_dto(_raw_invoice())
    assert dto.amount == 1180.0


# ── 6. vat_amount maps from VAT ──────────────────────────────────────────────

def test_vat_amount_mapped():
    dto = _map_to_dto(_raw_invoice())
    assert dto.vat_amount == 180.0


# ── 7. direction=incoming when buyer_inn==own_inn ────────────────────────────

def test_direction_incoming_when_buyer_is_own():
    raw = _raw_invoice()
    dto = _map_to_dto(raw, own_inn="999888777")
    assert dto.direction == "incoming"


# ── 8. direction=outgoing when seller_inn==own_inn ───────────────────────────

def test_direction_outgoing_when_seller_is_own():
    raw = _raw_invoice()
    dto = _map_to_dto(raw, own_inn="405176367")
    assert dto.direction == "outgoing"


# ── 9. direction=unknown when own_inn not set ────────────────────────────────

def test_direction_unknown_without_own_inn():
    dto = _map_to_dto(_raw_invoice(), own_inn="")
    assert dto.direction == "unknown"


# ── 10. waybill_number maps from OVERHEAD_NO ─────────────────────────────────

def test_waybill_number_from_overhead_no():
    dto = _map_to_dto(_raw_invoice())
    assert dto.waybill_number == "WB001"


# ── 11. source_hash deterministic for same input ─────────────────────────────

def test_source_hash_deterministic():
    dto1 = _map_to_dto(_raw_invoice())
    dto2 = _map_to_dto(_raw_invoice())
    assert dto1.source_hash() == dto2.source_hash()


# ── 12. source_hash changes if amount changes ────────────────────────────────

def test_source_hash_changes_with_amount():
    raw1 = _raw_invoice()
    raw2 = {**_raw_invoice(), "TOTAL": 2000.0}
    dto1 = _map_to_dto(raw1)
    dto2 = _map_to_dto(raw2)
    assert dto1.source_hash() != dto2.source_hash()
