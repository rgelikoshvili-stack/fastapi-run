"""tests/unit/test_document_intelligence.py
Unit tests for the Document Intelligence Engine components.
"""
import pytest
from decimal import Decimal


# ── contract_classifier ──────────────────────────────────────────────────────

from app.api.services.contract_classifier import (
    classify_provider_type,
    needs_pit_withholding,
    ProviderType,
)


def test_classify_shps_from_name():
    assert classify_provider_type("შპს ტექსელი") == ProviderType.SHPS


def test_classify_im_from_name():
    assert classify_provider_type("ი.მ. გელიკოშვილი") == ProviderType.IM


def test_classify_fp_from_name():
    assert classify_provider_type("ფ.პ. ივანე ბერიძე") == ProviderType.FP


def test_classify_sp_from_name():
    assert classify_provider_type("სს ბანკი") == ProviderType.SP


def test_classify_fp_from_11digit_inn():
    assert classify_provider_type(None, "12345678901") == ProviderType.FP


def test_classify_shps_from_9digit_inn():
    assert classify_provider_type(None, "123456789") == ProviderType.SHPS


def test_pit_required_for_fp():
    assert needs_pit_withholding(ProviderType.FP) is True


def test_pit_required_for_im():
    assert needs_pit_withholding(ProviderType.IM) is True


def test_no_pit_for_shps():
    assert needs_pit_withholding(ProviderType.SHPS) is False


# ── taxation_engine ──────────────────────────────────────────────────────────

from app.api.services.taxation_engine import (
    calculate_vat,
    calculate_service_pit,
    calculate_payroll,
    calculate_cit,
    calculate_dividend_withholding,
    analyse_document_taxes,
)


def test_vat_exclusive():
    r = calculate_vat(1000, inclusive=False)
    assert r["vat_amount"] == 180.0
    assert r["total"] == 1180.0
    assert r["net_amount"] == 1000.0


def test_vat_inclusive():
    r = calculate_vat(1180, inclusive=True)
    assert abs(r["vat_amount"] - 180.0) < 0.02
    assert abs(r["net_amount"] - 1000.0) < 0.02
    assert r["total"] == 1180.0


def test_service_pit_3000():
    r = calculate_service_pit(Decimal("3000"))
    assert r["pit"] == 600.0
    assert r["employee_pension"] == 60.0
    assert r["employer_pension"] == 60.0
    assert r["net_to_person"] == pytest.approx(3000 - 600 - 60, abs=0.01)


def test_payroll_resident():
    r = calculate_payroll(Decimal("3000"))
    assert r["pit"] == 600.0
    assert r["employee_pension"] == 60.0
    assert r["net"] == pytest.approx(3000 - 600 - 60, abs=0.01)


def test_cit_calculation():
    r = calculate_cit(Decimal("85000"))
    # tax_base = 85000 / 0.85 = 100000, cit = 15000
    assert abs(r["tax_base"] - 100000.0) < 0.01
    assert abs(r["cit"] - 15000.0) < 0.01


def test_dividend_withholding():
    r = calculate_dividend_withholding(Decimal("10000"))
    assert r["withholding_tax"] == 500.0
    assert r["net_to_shareholder"] == 9500.0


def test_analyse_document_taxes_fp_purchase():
    r = analyse_document_taxes(
        doc_type="invoice",
        total_amount=5000,
        provider_type="fp",
        is_our_purchase=True,
        vat_inclusive=False,
    )
    assert r["requires_pit"] is True
    assert r["pit_detail"] is not None
    assert r["pit_detail"]["pit"] == 1000.0


def test_analyse_document_taxes_shps_no_pit():
    r = analyse_document_taxes(
        doc_type="tax_invoice",
        total_amount=5000,
        provider_type="shps",
        is_our_purchase=True,
    )
    assert r["requires_pit"] is False
    assert r["pit_detail"] is None
    assert r["requires_vat"] is True


# ── document_extractor ───────────────────────────────────────────────────────

from app.api.services.document_extractor import _regex_extract, _extract_tax_invoice_inns


def test_extract_tax_invoice():
    text = "ანგარიშ-ფაქტურა №AA-123 2024-01-15\nგამყიდველი: შპს ტექს 123456789\nმყიდველი: 987654321\nთანხა: 1180.00"
    doc = _regex_extract(text)
    assert doc.document_type == "tax_invoice"


# ── Fix 1: field-number INN extraction ───────────────────────────────────────

def test_tax_invoice_inn_extraction_field_numbers():
    """ეა-85 ფაქტურა: seller=5.1, buyer=6.1 field pattern."""
    text = (
        "საქართველოს საგადასახადო ანგარიშ-ფაქტურა\n"
        "სერია ეა-85 4878150\n"
        "5.1 საიდ.ნომერი: 406039950\n"
        "5.2 გამყიდველი: Net Sky LLC\n"
        "6.1 საიდ.ნომერი: 202192643\n"
        "6.2 მყიდველი: ალტე შპს\n"
        "სულ დასარიცხი დღგ: 540.00\n"
    )
    seller, buyer, series, vat, _ = _extract_tax_invoice_inns(text)
    assert seller == "406039950", f"Expected seller 406039950, got {seller}"
    assert buyer == "202192643", f"Expected buyer 202192643, got {buyer}"
    assert series is not None and "4878150" in series
    assert vat == pytest.approx(540.0, abs=0.01)


def test_tax_invoice_inn_extraction_via_regex_extract():
    """_regex_extract should use field-number patterns for tax invoices."""
    text = (
        "ანგარიშ-ფაქტურა\n"
        "5.1  406039950\n"
        "6.1  202192643\n"
        "თანხა: 1180.00\n"
    )
    doc = _regex_extract(text)
    assert doc.seller_inn == "406039950"
    assert doc.buyer_inn == "202192643"


def test_tax_invoice_inn_fallback_keyword():
    """Georgian keyword fallback: 'მყიდველი' must not match inside 'გამყიდველი'."""
    text = "ანგარიშ-ფაქტურა\nგამყიდველი: 123456789\nმყიდველი: 987654321\nთანხა: 590.00"
    doc = _regex_extract(text)
    assert doc.seller_inn == "123456789"
    assert doc.buyer_inn == "987654321"


def test_extract_waybill():
    text = "სასაქონლო ზედნადები №WB-001 გამყიდველი: 123456789"
    doc = _regex_extract(text)
    assert doc.document_type == "waybill"


def test_extract_contract():
    text = "ხელშეკრულება №C-2024-01 მხარეები: შპს Alpha 123456789"
    doc = _regex_extract(text)
    assert doc.document_type == "contract"


def test_extract_act():
    text = "მიღება-ჩაბარების აქტი №A-001 2024-02-01 გამყიდველი: 123456789"
    doc = _regex_extract(text)
    assert doc.document_type == "act"


def test_extract_populates_flat_aliases():
    text = "ანგარიშ-ფაქტურა №TI-002\nგამყიდველი: 123456789\nმყიდველი: 987654321\nთანხა 590.00"
    doc = _regex_extract(text)
    assert doc.seller_inn == doc.seller.inn
    assert doc.buyer_inn == doc.buyer.inn


# ── completeness_checker ─────────────────────────────────────────────────────

from app.api.services.completeness_checker import check_document_set


def test_completeness_goods_all_present():
    docs = [
        {"doc_type": "waybill",     "doc_number": "WB-1", "total_amount": 1000, "seller_inn": "111", "buyer_inn": "222"},
        {"doc_type": "tax_invoice", "doc_number": "TI-1", "total_amount": 1000, "seller_inn": "111", "buyer_inn": "222"},
        {"doc_type": "invoice",     "doc_number": "INV-1","total_amount": 1000, "seller_inn": "111", "buyer_inn": "222"},
    ]
    r = check_document_set(docs, flow="goods")
    assert r["missing_count"] == 0
    assert r["ready_to_post"] is True
    assert "✅" in r["summary"]


def test_completeness_goods_missing_invoice():
    docs = [
        {"doc_type": "waybill",     "doc_number": "WB-1", "total_amount": 1000},
        {"doc_type": "tax_invoice", "doc_number": "TI-1", "total_amount": 1000},
    ]
    r = check_document_set(docs, flow="goods")
    assert r["missing_count"] == 1
    assert r["indicators"]["invoice"]["status"] == "missing"
    assert r["ready_to_post"] is False


def test_completeness_goods_amount_mismatch():
    docs = [
        {"doc_type": "waybill",     "total_amount": 1000},
        {"doc_type": "tax_invoice", "total_amount": 1200},
        {"doc_type": "invoice",     "total_amount": 1000},
    ]
    r = check_document_set(docs, flow="goods")
    assert len(r["alerts"]) > 0
    assert any("თანხ" in a for a in r["alerts"])


def test_completeness_service_flow():
    docs = [
        {"doc_type": "contract",    "doc_number": "CT-1", "total_amount": 5000},
        {"doc_type": "act",         "doc_number": "ACT-1","total_amount": 5000},
        {"doc_type": "tax_invoice", "doc_number": "TI-1", "total_amount": 5000},
    ]
    r = check_document_set(docs, flow="service")
    assert r["missing_count"] == 0
    assert r["ready_to_post"] is True


def test_completeness_auto_detect_goods():
    docs = [{"doc_type": "waybill", "total_amount": 100}]
    r = check_document_set(docs, flow="auto")
    assert r["flow"] == "goods"


def test_completeness_auto_detect_service():
    docs = [{"doc_type": "contract", "total_amount": 100}]
    r = check_document_set(docs, flow="auto")
    assert r["flow"] == "service"


# ── triangle_matcher ─────────────────────────────────────────────────────────

from app.api.services.triangle_matcher import compute_match_score


def test_triangle_full_match():
    wb  = {"total_amount": 1000, "seller_inn": "111", "buyer_inn": "222", "waybill_date": "2024-01-10"}
    ti  = {"total_amount": 1000, "seller_inn": "111", "buyer_inn": "222", "invoice_date": "2024-01-10", "related_waybill_number": None}
    inv = {"total_amount": 1000}
    r = compute_match_score(wb, ti, inv)
    assert r["score"] >= 0.6
    assert "amount_mismatch" not in r["mismatches"]


def test_triangle_amount_mismatch():
    wb  = {"total_amount": 1000, "seller_inn": "111", "buyer_inn": "222"}
    ti  = {"total_amount": 1200, "seller_inn": "111", "buyer_inn": "222"}
    r = compute_match_score(wb, ti, None)
    assert "amount_mismatch" in r["mismatches"]


def test_triangle_inn_mismatch():
    wb  = {"total_amount": 1000, "seller_inn": "111", "buyer_inn": "222"}
    ti  = {"total_amount": 1000, "seller_inn": "999", "buyer_inn": "222"}
    r = compute_match_score(wb, ti, None)
    assert "seller_inn_mismatch" in r["mismatches"]


def test_triangle_partial_missing():
    r = compute_match_score(None, None, None)
    assert r["score"] == 0.0
