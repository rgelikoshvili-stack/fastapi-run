"""
tests/integration/test_comment_propagation.py — Phase 4

Verify that invoice comment propagates to:
  1. waybill.notes (goods invoices)
  2. tax_invoice.notes (all invoices)
Requires DATABASE_URL.
"""
import os
import pytest

DB_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="DATABASE_URL not set — skipping comment propagation tests",
)

from app.api.services.invoice_creator import create_draft, finalize

TENANT = "test_comment_tenant"
COMMENT = "გადახდის ვადა: 30 დღე — Prepayment required"


@pytest.fixture(scope="module")
def db_conn():
    import psycopg2
    conn = psycopg2.connect(DB_URL)
    yield conn
    conn.rollback()
    conn.close()


def test_comment_propagates_to_waybill_and_tax_invoice(db_conn):
    """Goods invoice: comment → waybill.notes + tax_invoice.notes."""
    import psycopg2.extras

    draft = create_draft(db_conn, TENANT, {
        "invoice_type": "goods",
        "buyer_inn": "205111111",
        "buyer_name": "Buyer Ltd",
        "line_items": [{"description": "Widget", "qty": 1, "unit_price": 100.00}],
        "comment": COMMENT,
    })
    result = finalize(db_conn, TENANT, draft["id"])

    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # waybill.notes
    cur.execute("SELECT notes FROM waybills WHERE id = %s", (result["waybill_id"],))
    wb_row = cur.fetchone()
    assert wb_row is not None
    assert wb_row["notes"] == COMMENT

    # tax_invoice.notes
    cur.execute("SELECT notes FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    ti_row = cur.fetchone()
    assert ti_row is not None
    assert ti_row["notes"] == COMMENT

    # cleanup
    cur.execute("DELETE FROM waybills WHERE id = %s", (result["waybill_id"],))
    cur.execute("DELETE FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft["id"],))
    db_conn.commit()
    cur.close()


def test_comment_propagates_to_tax_invoice_only_for_service(db_conn):
    """Service invoice: comment → only tax_invoice.notes (no waybill)."""
    import psycopg2.extras

    draft = create_draft(db_conn, TENANT, {
        "invoice_type": "service",
        "buyer_inn": "205222222",
        "buyer_name": "Service Client",
        "line_items": [{"description": "Consulting", "qty": 1, "unit_price": 0, "amount": 500.00}],
        "comment": COMMENT,
    })
    result = finalize(db_conn, TENANT, draft["id"])

    assert result["waybill_id"] is None

    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT notes FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    ti_row = cur.fetchone()
    assert ti_row is not None
    assert ti_row["notes"] == COMMENT

    # cleanup
    cur.execute("DELETE FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft["id"],))
    db_conn.commit()
    cur.close()


def test_empty_comment_propagates_as_empty_string(db_conn):
    """No comment → notes stored as empty string (not NULL)."""
    import psycopg2.extras

    draft = create_draft(db_conn, TENANT, {
        "invoice_type": "service",
        "buyer_inn": "205333333",
        "buyer_name": "No Comment Co",
        "line_items": [{"description": "Work", "qty": 1, "unit_price": 0, "amount": 200.00}],
        # comment omitted intentionally
    })
    result = finalize(db_conn, TENANT, draft["id"])

    cur = db_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT notes FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    ti_row = cur.fetchone()
    assert ti_row is not None
    # comment is None → finalize passes "" → notes stored as ""
    assert (ti_row["notes"] or "") == ""

    # cleanup
    cur.execute("DELETE FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft["id"],))
    db_conn.commit()
    cur.close()


def test_journal_entries_contain_invoice_number(db_conn):
    """Journal entry notes reference the invoice number."""
    draft = create_draft(db_conn, TENANT, {
        "invoice_type": "service",
        "buyer_inn": "205444444",
        "buyer_name": "Journal Test",
        "line_items": [{"description": "Service", "qty": 1, "unit_price": 0, "amount": 300.00}],
        "comment": "test",
    })
    result = finalize(db_conn, TENANT, draft["id"])

    inv_num = result["invoice_number"]
    entries = result["journal_entries"]
    assert any(inv_num in (e.get("note") or "") for e in entries)

    # cleanup
    cur = db_conn.cursor()
    cur.execute("DELETE FROM tax_invoices WHERE id = %s", (result["tax_invoice_id"],))
    cur.execute("DELETE FROM outgoing_invoices WHERE id = %s", (draft["id"],))
    db_conn.commit()
    cur.close()
