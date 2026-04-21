"""
tests/integration/test_triangle_matcher.py — Phase 4

Tests for triangle reconciliation logic:
- compute_match_score (unit, no DB)
- find_candidates + upsert_triangle_match (requires DATABASE_URL)
"""
import os
import pytest
from decimal import Decimal

DB_URL = os.environ.get("DATABASE_URL")

# Only DB tests skip when DATABASE_URL is absent — unit tests always run
_needs_db = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")

from app.api.services.triangle_matcher import compute_match_score, upsert_triangle_match


# ── Unit tests (no DB) ────────────────────────────────────────────────────────

class TestComputeMatchScore:

    def test_full_match_three_docs(self):
        wb = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "1180.00", "waybill_date": "2025-01-15"}
        ti = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "1180.00", "invoice_date": "2025-01-15", "related_waybill_number": "WB-001"}
        ci = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "1180.00", "invoice_date": "2025-01-15"}
        # add waybill_number to wb for cross-ref check
        wb["waybill_number"] = "WB-001"
        result = compute_match_score(wb, ti, ci)
        assert result["score"] > 0.7
        assert result["status"] == "full"
        assert result["mismatches"] == []

    def test_amount_mismatch_detected(self):
        wb = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "1180.00", "waybill_date": "2025-01-15"}
        ti = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "999.00", "invoice_date": "2025-01-15"}
        result = compute_match_score(wb, ti, None)
        assert "amount_mismatch" in result["mismatches"]
        assert result["status"] == "mismatch"

    def test_inn_mismatch_detected(self):
        wb = {"seller_inn": "111111111", "buyer_inn": "222222222", "total_amount": "500.00", "waybill_date": "2025-02-01"}
        ti = {"seller_inn": "999999999", "buyer_inn": "222222222", "total_amount": "500.00", "invoice_date": "2025-02-01"}
        result = compute_match_score(wb, ti, None)
        assert "seller_inn_mismatch" in result["mismatches"]

    def test_partial_match_two_docs(self):
        wb = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "2360.00", "waybill_date": "2025-03-10"}
        result = compute_match_score(wb, None, None)
        assert result["score"] > 0
        assert result["status"] in ("partial", "full")

    def test_empty_docs_returns_zero(self):
        result = compute_match_score(None, None, None)
        assert result["score"] == 0.0
        assert result["status"] == "partial"

    def test_amount_tolerance_within_5_tetri(self):
        wb = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "1000.00", "waybill_date": "2025-01-01"}
        ti = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "1000.03", "invoice_date": "2025-01-01"}
        result = compute_match_score(wb, ti, None)
        assert "amount_mismatch" not in result["mismatches"]

    def test_waybill_number_cross_reference(self):
        wb = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "500.00", "waybill_date": "2025-01-10", "waybill_number": "ZN-2025-001"}
        ti = {"seller_inn": "100000001", "buyer_inn": "200000002", "total_amount": "500.00", "invoice_date": "2025-01-10", "related_waybill_number": "ZN-2025-001"}
        result = compute_match_score(wb, ti, None)
        assert result["score"] >= 0.80

    def test_score_bounded_0_to_1(self):
        wb = {"seller_inn": "A", "buyer_inn": "B", "total_amount": "100", "waybill_date": "2025-01-01", "waybill_number": "X"}
        ti = {"seller_inn": "A", "buyer_inn": "B", "total_amount": "100", "invoice_date": "2025-01-01", "related_waybill_number": "X"}
        ci = {"seller_inn": "A", "buyer_inn": "B", "total_amount": "100", "invoice_date": "2025-01-01"}
        result = compute_match_score(wb, ti, ci)
        assert 0.0 <= result["score"] <= 1.0


# ── DB tests ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_conn():
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    yield conn
    conn.rollback()
    conn.close()


@_needs_db
def test_upsert_triangle_match_creates_row(db_conn):
    """INSERT a triangle match and verify it round-trips."""
    import psycopg2.extras
    tenant_id = "test_triangle_tenant"
    match_data = {
        "waybill_id": None,
        "tax_invoice_id": None,
        "commercial_invoice_id": None,
        "match_score": 0.85,
        "match_status": "partial",
        "mismatch_fields": [],
        "waybill_total": 1180.00,
        "tax_invoice_total": 1180.00,
        "commercial_invoice_total": None,
        "amount_diff": None,
    }
    match_id = upsert_triangle_match(db_conn, tenant_id, match_data)
    assert isinstance(match_id, int)
    assert match_id > 0

    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM triangle_matches WHERE id = %s", (match_id,))
    row = cur.fetchone()
    cur.close()
    assert row is not None
    assert float(row["match_score"]) == pytest.approx(0.85, abs=0.001)
    assert row["match_status"] == "partial"
    assert row["tenant_id"] == tenant_id

    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM triangle_matches WHERE id = %s", (match_id,))
    db_conn.commit()
    cur.close()
