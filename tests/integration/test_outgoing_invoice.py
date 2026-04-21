"""
tests/integration/test_outgoing_invoice.py — Phase 4

Full flow: draft → auto-save → finalize → verify waybill + tax_invoice generated.
Requires DATABASE_URL.
"""
import os
import json
import pytest

DB_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="DATABASE_URL not set — skipping outgoing invoice tests",
)

from app.api.services.invoice_creator import (
    create_draft, update_draft, finalize, list_invoices
)


@pytest.fixture(scope="module")
def db_conn():
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    yield conn
    conn.rollback()
    conn.close()


TENANT = "test_outgoing_tenant"

GOODS_PAYLOAD = {
    "invoice_type": "goods",
    "buyer_inn": "205123456",
    "buyer_name": "Tech Corp",
    "buyer_email": "buyer@corp.ge",
    "transport_from": "Tbilisi",
    "transport_to": "Batumi",
    "vehicle_number": "GD 001 AA",
    "driver_name": "Giorgi Chikobava",
    "line_items": [
        {"description": "Laptop", "qty": 2, "unit_price": 1500.00},
        {"description": "Monitor", "qty": 3, "unit_price": 400.00},
    ],
    "comment": "Payment within 30 days",
}

SERVICE_PAYLOAD = {
    "invoice_type": "service",
    "buyer_inn": "205654321",
    "buyer_name": "Design Studio",
    "buyer_email": "studio@design.ge",
    "line_items": [
        {"description": "UI Design", "qty": 1, "unit_price": 0, "amount": 2000.00},
        {"description": "Branding", "qty": 1, "unit_price": 0, "amount": 800.00},
    ],
    "comment": "Prepayment required",
}


# ── Totals calculation ────────────────────────────────────────────────────────

def test_goods_totals_calculated():
    """Subtotal, VAT (18%), total are correctly computed."""
    conn = __import__("psycopg2").connect(DB_URL)
    draft = create_draft(conn, TENANT, GOODS_PAYLOAD)
    conn.close()
    # 2*1500 + 3*400 = 4200; vat=756; total=4956
    assert float(draft["subtotal"]) == pytest.approx(4200.00, abs=0.01)
    assert float(draft["vat_amount"]) == pytest.approx(756.00, abs=0.01)
    assert float(draft["total_amount"]) == pytest.approx(4956.00, abs=0.01)

    # cleanup
    conn2 = __import__("psycopg2").connect(DB_URL)
    cur = conn2.cursor()
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s AND tenant_id = %s", (draft["id"], TENANT))
    conn2.commit()
    cur.close()
    conn2.close()


def test_service_totals_calculated():
    """Service invoice: amount field used instead of qty*price."""
    conn = __import__("psycopg2").connect(DB_URL)
    draft = create_draft(conn, TENANT, SERVICE_PAYLOAD)
    conn.close()
    # 2000 + 800 = 2800; vat=504; total=3304
    assert float(draft["subtotal"]) == pytest.approx(2800.00, abs=0.01)
    assert float(draft["vat_amount"]) == pytest.approx(504.00, abs=0.01)
    assert float(draft["total_amount"]) == pytest.approx(3304.00, abs=0.01)

    conn2 = __import__("psycopg2").connect(DB_URL)
    cur = conn2.cursor()
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s AND tenant_id = %s", (draft["id"], TENANT))
    conn2.commit()
    cur.close()
    conn2.close()


# ── Draft lifecycle ────────────────────────────────────────────────────────────

def test_create_draft_status_is_draft(db_conn):
    draft = create_draft(db_conn, TENANT, GOODS_PAYLOAD)
    assert draft["status"] == "draft"
    assert draft["id"] > 0
    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft["id"],))
    db_conn.commit()
    cur.close()


def test_autosave_updates_buyer_name(db_conn):
    draft = create_draft(db_conn, TENANT, GOODS_PAYLOAD)
    draft_id = draft["id"]
    updated = update_draft(db_conn, TENANT, draft_id, {"buyer_name": "Updated Corp"})
    assert updated["buyer_name"] == "Updated Corp"
    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft_id,))
    db_conn.commit()
    cur.close()


def test_autosave_nonexistent_raises_lookup(db_conn):
    with pytest.raises(LookupError):
        update_draft(db_conn, TENANT, 999999999, {"buyer_name": "X"})


def test_invalid_invoice_type_raises(db_conn):
    bad = {**GOODS_PAYLOAD, "invoice_type": "wrong"}
    with pytest.raises(ValueError):
        create_draft(db_conn, TENANT, bad)


# ── Finalize flow ─────────────────────────────────────────────────────────────

def test_finalize_goods_generates_waybill_and_tax_invoice(db_conn):
    """Full flow: create goods draft → finalize → waybill + tax_invoice exist."""
    import psycopg2.extras
    draft = create_draft(db_conn, TENANT, GOODS_PAYLOAD)
    draft_id = draft["id"]

    result = finalize(db_conn, TENANT, draft_id)

    assert result["invoice_number"].startswith("INV-")
    assert result["waybill_id"] is not None
    assert result["tax_invoice_id"] is not None
    assert len(result["journal_entries"]) == 2

    # Verify waybill exists
    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM waybills WHERE id = %s AND tenant_id = %s",
                (result["waybill_id"], TENANT))
    wb = cur.fetchone()
    assert wb is not None
    assert wb["status"] == "imported"

    # Verify tax_invoice exists
    cur.execute("SELECT * FROM tax_invoices WHERE id = %s AND tenant_id = %s",
                (result["tax_invoice_id"], TENANT))
    ti = cur.fetchone()
    assert ti is not None

    # Verify outgoing status = finalized
    cur.execute("SELECT status, invoice_number FROM outgoing_invoices WHERE id = %s", (draft_id,))
    row = cur.fetchone()
    assert row["status"] == "finalized"
    assert row["invoice_number"] == result["invoice_number"]

    # cleanup
    cur.execute("DELETE FROM waybills WHERE id = %s", (result["waybill_id"],))
    cur.execute("DELETE FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft_id,))
    db_conn.commit()
    cur.close()


def test_finalize_service_generates_only_tax_invoice(db_conn):
    """Service invoice: no waybill, only tax_invoice."""
    draft = create_draft(db_conn, TENANT, SERVICE_PAYLOAD)
    result = finalize(db_conn, TENANT, draft["id"])

    assert result["waybill_id"] is None
    assert result["tax_invoice_id"] is not None

    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft["id"],))
    db_conn.commit()
    cur.close()


def test_double_finalize_raises_value_error(db_conn):
    """Finalizing an already-finalized invoice must raise."""
    draft = create_draft(db_conn, TENANT, SERVICE_PAYLOAD)
    result = finalize(db_conn, TENANT, draft["id"])

    with pytest.raises(ValueError, match="already"):
        finalize(db_conn, TENANT, draft["id"])

    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft["id"],))
    db_conn.commit()
    cur.close()


def test_invoice_number_increments(db_conn):
    """Second invoice for same tenant gets a higher counter."""
    draft1 = create_draft(db_conn, TENANT, SERVICE_PAYLOAD)
    draft2 = create_draft(db_conn, TENANT, SERVICE_PAYLOAD)
    r1 = finalize(db_conn, TENANT, draft1["id"])
    r2 = finalize(db_conn, TENANT, draft2["id"])

    num1 = int(r1["invoice_number"].split("-")[-1])
    num2 = int(r2["invoice_number"].split("-")[-1])
    assert num2 > num1

    # cleanup
    cur = db_conn.cursor()
    for inv_id, ti_id in [(draft1["id"], r1["tax_invoice_id"]), (draft2["id"], r2["tax_invoice_id"])]:
        cur.execute("DELETE FROM tax_invoices WHERE id = %s", (ti_id,))
        cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (inv_id,))
    db_conn.commit()
    cur.close()


def test_list_invoices(db_conn):
    """list_invoices returns items for the tenant."""
    result = list_invoices(db_conn, TENANT, limit=10, offset=0)
    assert "total" in result
    assert "items" in result
    assert isinstance(result["items"], list)
