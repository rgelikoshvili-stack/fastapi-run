"""
tests/integration/test_duplicate_prevention.py
Verifies that posting a suspected duplicate invoice returns DUPLICATE_INVOICE_WARNING.
Requires DATABASE_URL (live DB). Cleans up after itself.
"""
import os
import pytest
import psycopg2

DB_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")

TENANT = "test_dup_detection"


def _get_conn():
    return psycopg2.connect(DB_URL)


def _insert_draft(partner: str, amount: float, date: str, status: str = "approved") -> int:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO journal_drafts
            (tenant_id, description, partner, amount, account_code, status, date, created_at)
        VALUES (%s, 'Dup test', %s, %s, '7510', %s, %s, NOW())
        RETURNING id
        """,
        (TENANT, partner, amount, status, date),
    )
    draft_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return draft_id


def _delete_drafts(*ids):
    if not ids:
        return
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM journal_drafts WHERE id = ANY(%s)", (list(ids),))
    conn.commit()
    cur.close()
    conn.close()


def test_duplicate_invoice_detected():
    """Second draft with same partner+amount within ±3 days triggers DUPLICATE_INVOICE_WARNING."""
    from app.api.services.posting_service import _check_duplicate_invoice
    import psycopg2.extras

    original_id = _insert_draft("TBC Bank", 1500.00, "2025-01-15", status="approved")
    new_id = _insert_draft("TBC Bank", 1500.00, "2025-01-17", status="approved")

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        draft = {
            "id": new_id,
            "partner": "TBC Bank",
            "amount": 1500.00,
            "date": "2025-01-17",
        }
        dup = _check_duplicate_invoice(cur, draft, TENANT)
        cur.close()
        conn.close()

        assert dup is not None, "Should detect duplicate"
        assert dup["id"] == original_id
    finally:
        _delete_drafts(original_id, new_id)


def test_no_duplicate_different_partner():
    """Different partner → no duplicate warning."""
    from app.api.services.posting_service import _check_duplicate_invoice
    import psycopg2.extras

    original_id = _insert_draft("TBC Bank", 1500.00, "2025-01-15", status="approved")
    new_id = _insert_draft("Bank of Georgia", 1500.00, "2025-01-17", status="approved")

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        draft = {
            "id": new_id,
            "partner": "Bank of Georgia",
            "amount": 1500.00,
            "date": "2025-01-17",
        }
        dup = _check_duplicate_invoice(cur, draft, TENANT)
        cur.close()
        conn.close()

        assert dup is None, "Different partner should not trigger duplicate"
    finally:
        _delete_drafts(original_id, new_id)


def test_no_duplicate_outside_date_window():
    """Same partner+amount but >3 days apart → no duplicate."""
    from app.api.services.posting_service import _check_duplicate_invoice
    import psycopg2.extras

    original_id = _insert_draft("TBC Bank", 1500.00, "2025-01-01", status="approved")
    new_id = _insert_draft("TBC Bank", 1500.00, "2025-01-15", status="approved")

    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        draft = {
            "id": new_id,
            "partner": "TBC Bank",
            "amount": 1500.00,
            "date": "2025-01-15",
        }
        dup = _check_duplicate_invoice(cur, draft, TENANT)
        cur.close()
        conn.close()

        assert dup is None, "14 days apart should not trigger duplicate"
    finally:
        _delete_drafts(original_id, new_id)
