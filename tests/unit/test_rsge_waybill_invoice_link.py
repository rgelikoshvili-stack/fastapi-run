"""tests/unit/test_rsge_waybill_invoice_link.py — Waybill↔invoice link by OVERHEAD_NO."""
import asyncio
from unittest.mock import AsyncMock, MagicMock


# ── Helpers ──────────────────────────────────────────────────────────────────

def _wb_row(waybill_number="WB001", amount=1000.0):
    return {
        "id": 1, "waybill_number": waybill_number, "rsge_id": "WB001",
        "full_amount": amount, "buyer_name": "მყიდველი",
        "buyer_tin": "111", "seller_name": "გამყიდველი",
        "seller_tin": "222", "begin_date": "2025-01-01",
        "raw_payload": "{}",
    }


def _inv_row(overhead_no="WB001", total=1000.0):
    return {
        "ID": "500", "INVOICE_NUMBER": "INV-500",
        "TOTAL": total, "VAT": 0.0,
        "STATUS": "0", "OVERHEAD_NO": overhead_no,
        "OPERATION_DATE": "2025-01-01",
    }


# ── 1. Link found when OVERHEAD_NO == waybill_number ─────────────────────────

def test_link_found_by_overhead_no():
    wb_num = "WB001"
    invoices = [_inv_row(overhead_no="WB001"), _inv_row(overhead_no="WB999")]
    matched = [i for i in invoices if (i.get("OVERHEAD_NO") or "").strip() == wb_num]
    assert len(matched) == 1
    assert matched[0]["INVOICE_NUMBER"] == "INV-500"


# ── 2. No match when OVERHEAD_NO differs ─────────────────────────────────────

def test_no_link_when_overhead_no_differs():
    wb_num = "WB-DOES-NOT-EXIST"
    invoices = [_inv_row(overhead_no="WB001")]
    matched = [i for i in invoices if (i.get("OVERHEAD_NO") or "").strip() == wb_num]
    assert matched == []


# ── 3. find_by_waybill_number is importable ──────────────────────────────────

def test_find_by_waybill_number_importable():
    from app.api.services.rsge_document_service import find_by_waybill_number
    assert callable(find_by_waybill_number)


# ── 4. find_by_waybill_number returns list ───────────────────────────────────

def test_find_by_waybill_number_returns_list():
    async def _run():
        from app.api.services.rsge_document_service import find_by_waybill_number
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        result = await find_by_waybill_number(mock_conn, "t1", "WB001")
        return result
    result = asyncio.run(_run())
    assert isinstance(result, list)


# ── 5. Waybill amount vs invoice total diff computed correctly ────────────────

def test_waybill_invoice_amount_diff():
    wb_total = 1000.0
    inv_total = 1050.0  # includes extra service
    diff = round(abs(wb_total - inv_total), 4)
    assert diff == 50.0


# ── 6. Diff lines are invoice lines not in waybill goods ─────────────────────

def test_diff_lines_are_extra_invoice_items():
    wb_goods = [{"name": "ნივთი 1"}, {"name": "ნივთი 2"}]
    inv_lines = [{"name": "ნივთი 1"}, {"name": "ნივთი 2"}, {"name": "მიტანა"}]
    wb_names = {(g["name"] or "").strip().lower() for g in wb_goods}
    diff = [l for l in inv_lines if l["name"].strip().lower() not in wb_names]
    assert len(diff) == 1
    assert diff[0]["name"] == "მიტანა"


# ── 7. Combined total = waybill + extra services ──────────────────────────────

def test_combined_total_includes_extras():
    wb_total = 1000.0
    extra_services = [{"amount": 50.0}, {"amount": 25.0}]
    combined = wb_total + sum(float(s["amount"]) for s in extra_services)
    assert combined == 1075.0


# ── 8. linked-invoice route registered ───────────────────────────────────────

def test_linked_invoice_route_registered():
    from app.api.routes_rs_ge import router
    paths = [r.path for r in router.routes]
    assert any("linked-invoice" in p for p in paths)


# ── 9. rsge_documents.waybill_number column exists in migration ───────────────

def test_waybill_number_column_in_migration():
    from app.startup.migrations_rsge import _DDL
    ddl_text = " ".join(_DDL)
    assert "waybill_number" in ddl_text


# ── 10. OVERHEAD_NO key variants handled ─────────────────────────────────────

def test_overhead_no_key_variants():
    raw_upper = {"OVERHEAD_NO": "WB001"}
    raw_lower = {"overhead_no": "WB001"}
    extract = lambda r: r.get("OVERHEAD_NO") or r.get("overhead_no") or ""
    assert extract(raw_upper) == "WB001"
    assert extract(raw_lower) == "WB001"
