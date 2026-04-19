"""
tests/unit/test_decision_engine.py
Decision Engine unit tests — no DB, no AI API calls needed.
"""
import pytest
from decimal import Decimal


# ── normalize ────────────────────────────────────────────────────────────────

def test_normalize_text_basic():
    from app.api.services.decision_engine.normalize import normalize_text
    assert normalize_text("  Hello World!  ") == "hello world"
    assert normalize_text(None) == ""
    assert normalize_text("") == ""


def test_normalize_removes_stopwords():
    from app.api.services.decision_engine.normalize import normalize_text
    result = normalize_text("payment to the company for invoice")
    assert "the" not in result.split()
    assert "invoice" not in result.split()
    assert "payment" not in result.split()


def test_parse_amount_no_vat():
    from app.api.services.decision_engine.normalize import parse_amount
    r = parse_amount(1000)
    assert r["gross"] == 1000.0
    assert r["vat"] == 0.0
    assert r["vat_included"] is None


def test_parse_amount_vat_inclusive():
    from app.api.services.decision_engine.normalize import parse_amount
    r = parse_amount(1180, vat_inclusive=True)
    assert abs(r["net"] - 1000.0) < 0.02
    assert abs(r["vat"] - 180.0) < 0.02
    assert r["vat_included"] is True


def test_parse_amount_vat_exclusive():
    from app.api.services.decision_engine.normalize import parse_amount
    r = parse_amount(1000, vat_inclusive=False)
    assert r["net"] == 1000.0
    assert abs(r["vat"] - 180.0) < 0.02
    assert r["gross"] == pytest.approx(1180.0, abs=0.02)


def test_detect_vat_flag():
    from app.api.services.decision_engine.normalize import detect_vat_flag
    assert detect_vat_flag("VAT included") is True
    assert detect_vat_flag("excl. VAT") is False
    assert detect_vat_flag("normal text") is None
    assert detect_vat_flag(None) is None


def test_normalize_partner():
    from app.api.services.decision_engine.normalize import normalize_partner
    assert "ltd" not in normalize_partner("ACME Ltd")
    assert "acme" in normalize_partner("ACME Ltd")


def test_partner_similarity_exact():
    from app.api.services.decision_engine.normalize import partner_similarity
    score = partner_similarity("TBC Bank", "TBC Bank")
    assert score >= 90


def test_partner_similarity_mismatch():
    from app.api.services.decision_engine.normalize import partner_similarity
    score = partner_similarity("TBC Bank", "Bank of Georgia")
    assert score < 80


# ── matcher ──────────────────────────────────────────────────────────────────

def test_exact_match_found():
    from app.api.services.decision_engine.matcher import exact_match

    invoice = {"description": "Wolt delivery", "amount": 150.0, "partner": "Wolt", "date": "2024-01-10"}
    candidates = [
        {"description": "Wolt delivery", "amount": 150.0, "partner": "Wolt", "date": "2024-01-10", "account_code": "7310"},
    ]
    result = exact_match(invoice, candidates)
    assert result is not None
    assert result["match_type"] == "exact"
    assert result["confidence"] >= 0.95


def test_exact_match_amount_mismatch():
    from app.api.services.decision_engine.matcher import exact_match

    invoice = {"description": "Wolt", "amount": 500.0, "partner": "Wolt", "date": "2024-01-10"}
    candidates = [
        {"description": "Wolt", "amount": 400.0, "partner": "Wolt", "date": "2024-01-10"},
    ]
    result = exact_match(invoice, candidates)
    assert result is None  # 20% diff → no exact match


def test_exact_match_partner_mismatch():
    from app.api.services.decision_engine.matcher import exact_match

    invoice = {"description": "Services", "amount": 200.0, "partner": "TBC Bank", "date": "2024-01-10"}
    candidates = [
        {"description": "Services", "amount": 200.0, "partner": "Bank of Georgia", "date": "2024-01-10"},
    ]
    result = exact_match(invoice, candidates)
    assert result is None


def test_calculate_confidence_weights():
    from app.api.services.decision_engine.matcher import calculate_confidence
    # Perfect scores → 1.0
    conf = calculate_confidence(1.0, 1.0, 1.0, 1.0)
    assert conf == pytest.approx(1.0)
    # Only amount perfect → 0.4
    conf = calculate_confidence(1.0, 0.0, 0.0, 0.0)
    assert conf == pytest.approx(0.4, abs=0.001)


def test_partial_match_no_candidates():
    from app.api.services.decision_engine.matcher import partial_match

    invoice = {"description": "Mixed invoice goods and services", "amount": 1200.0, "partner": "Vendor X"}
    result = partial_match(invoice, [])
    assert result["match_type"] == "partial"
    assert "lines" in result
    assert "residual" in result


# ── residual fallback ─────────────────────────────────────────────────────────

def test_residual_fallback_transport():
    from app.api.services.decision_engine.residual import _fallback_classify
    r = _fallback_classify("სატრანსპორტო ხარჯი", 50.0)
    assert r["account_code"] == "7310"
    assert r["confidence"] >= 0.5


def test_residual_fallback_bank_fee():
    from app.api.services.decision_engine.residual import _fallback_classify
    r = _fallback_classify("bank commission fee", 5.0)
    assert r["account_code"] == "7510"


def test_residual_fallback_unknown():
    from app.api.services.decision_engine.residual import _fallback_classify
    r = _fallback_classify("zzz unknown xyz", 20.0)
    assert r["account_code"] == "7990"
    assert r["status"] == "manual_review"


def test_residual_no_api_key(monkeypatch):
    """Without ANTHROPIC_API_KEY, should fall back gracefully."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from app.api.services.decision_engine import residual as m
    import importlib; importlib.reload(m)
    r = m.classify_residual("test", 100.0, {}, "default")
    assert "account_code" in r
    assert r["model_used"] == "fallback"
