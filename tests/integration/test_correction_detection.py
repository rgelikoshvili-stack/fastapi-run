"""
tests/integration/test_correction_detection.py — Phase 4

Tests for field-level correction detection:
- detect_corrections (unit, no DB)
- save_corrections + get_correction_history (requires DATABASE_URL)
- create_corrected_waybill version tracking (requires DATABASE_URL)
"""
import os
import pytest

DB_URL = os.environ.get("DATABASE_URL")

_needs_db = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")

from app.api.services.correction_detector import (
    detect_corrections, save_corrections, get_correction_history,
    create_corrected_waybill,
)


# ── Unit tests (no DB) ────────────────────────────────────────────────────────

class TestDetectCorrections:

    def test_no_changes(self):
        old = {"seller_inn": "100000001", "total_amount": "1000.00", "buyer_name": "Alte"}
        new = {"seller_inn": "100000001", "total_amount": "1000.00", "buyer_name": "Alte"}
        assert detect_corrections(old, new) == []

    def test_single_field_change(self):
        old = {"seller_inn": "100000001", "total_amount": "1000.00"}
        new = {"seller_inn": "100000001", "total_amount": "1500.00"}
        changes = detect_corrections(old, new)
        assert len(changes) == 1
        assert changes[0]["field_name"] == "total_amount"
        assert changes[0]["old_value"] == "1000.00"
        assert changes[0]["new_value"] == "1500.00"

    def test_multiple_fields_changed(self):
        old = {"seller_inn": "111111111", "buyer_inn": "222222222", "total_amount": "500.00"}
        new = {"seller_inn": "999999999", "buyer_inn": "222222222", "total_amount": "600.00"}
        changes = detect_corrections(old, new)
        fields = {c["field_name"] for c in changes}
        assert "seller_inn" in fields
        assert "total_amount" in fields
        assert "buyer_inn" not in fields

    def test_amount_normalized(self):
        """1000 and 1000.00 should be considered equal."""
        old = {"total_amount": "1000"}
        new = {"total_amount": "1000.00"}
        assert detect_corrections(old, new) == []

    def test_none_to_value(self):
        old = {"vehicle_number": None}
        new = {"vehicle_number": "GD 123 AB"}
        changes = detect_corrections(old, new)
        assert len(changes) == 1
        assert changes[0]["old_value"] is None
        assert changes[0]["new_value"] == "GD 123 AB"

    def test_value_to_none(self):
        old = {"driver_name": "Giorgi"}
        new = {"driver_name": None}
        changes = detect_corrections(old, new)
        assert len(changes) == 1
        assert changes[0]["old_value"] == "Giorgi"
        assert changes[0]["new_value"] is None

    def test_only_tracked_fields(self):
        """Changes to non-tracked fields are ignored."""
        old = {"untracked_field": "old", "total_amount": "100.00"}
        new = {"untracked_field": "new", "total_amount": "100.00"}
        changes = detect_corrections(old, new)
        assert changes == []


# ── DB tests ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def db_conn():
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    yield conn
    conn.rollback()
    conn.close()


def _insert_test_waybill(conn, tenant_id: str) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO waybills
            (tenant_id, waybill_number, waybill_date, seller_inn, seller_name,
             buyer_inn, buyer_name, total_amount, status, version)
        VALUES (%s,'WB-TEST-001','2025-01-15','100000001','Test Seller',
                '200000002','Test Buyer',1180.00,'imported',1)
        RETURNING id
        """,
        (tenant_id,),
    )
    wb_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    return wb_id


@_needs_db
def test_save_and_retrieve_corrections(db_conn):
    tenant_id = "test_correction_tenant"
    wb_id = _insert_test_waybill(db_conn, tenant_id)

    changes = [
        {"field_name": "total_amount", "old_value": "1180.00", "new_value": "1200.00"},
        {"field_name": "seller_inn", "old_value": "100000001", "new_value": "999999999"},
    ]
    saved = save_corrections(db_conn, tenant_id, "waybill", wb_id, changes,
                              corrected_by="test_user", note="test correction")
    assert saved == 2

    history = get_correction_history(db_conn, tenant_id, "waybill", wb_id)
    assert len(history) == 2
    fields = {h["field"] for h in history}
    assert "total_amount" in fields
    assert "seller_inn" in fields

    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM document_corrections WHERE doc_id = %s AND doc_type = 'waybill'", (wb_id,))
    cur.execute("DELETE FROM waybills WHERE id = %s", (wb_id,))
    db_conn.commit()
    cur.close()


@_needs_db
def test_create_corrected_waybill_version_tracking(db_conn):
    tenant_id = "test_correction_tenant"
    original_id = _insert_test_waybill(db_conn, tenant_id)

    new_data = {
        "waybill_number": "WB-TEST-001",
        "total_amount": "1360.00",
        "seller_inn": "100000001",
        "seller_name": "Test Seller",
        "buyer_inn": "200000002",
        "buyer_name": "Test Buyer",
        "waybill_date": "2025-01-15",
    }
    corrected = create_corrected_waybill(db_conn, tenant_id, original_id, new_data, "test_user")

    assert corrected["version"] == 2
    assert corrected["original_waybill_id"] == original_id
    assert float(corrected["total_amount"]) == pytest.approx(1360.00, abs=0.01)

    # original should be marked corrected
    cur = db_conn.cursor()
    cur.execute("SELECT status FROM waybills WHERE id = %s", (original_id,))
    orig_status = cur.fetchone()[0]
    assert orig_status == "corrected"

    # correction log should exist
    history = get_correction_history(db_conn, tenant_id, "waybill", corrected["id"])
    fields = {h["field"] for h in history}
    assert "total_amount" in fields

    # cleanup
    new_id = corrected["id"]
    cur.execute("DELETE FROM document_corrections WHERE doc_id IN (%s,%s) AND doc_type='waybill'", (original_id, new_id))
    cur.execute("DELETE FROM waybills WHERE id IN (%s,%s)", (original_id, new_id))
    db_conn.commit()
    cur.close()


@_needs_db
def test_empty_corrections_not_saved(db_conn):
    tenant_id = "test_correction_tenant"
    wb_id = _insert_test_waybill(db_conn, tenant_id)
    saved = save_corrections(db_conn, tenant_id, "waybill", wb_id, [], corrected_by="test")
    assert saved == 0

    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM waybills WHERE id = %s", (wb_id,))
    db_conn.commit()
    cur.close()
