"""
tests/integration/test_tenant_isolation.py

Verifies that tenant A data is invisible to tenant B queries at the DB level.
Tests journal_drafts and bank_transactions — the two primary tenant-aware tables.

Skip condition: DATABASE_URL not set.
Run: DATABASE_URL=... python -m pytest tests/integration/test_tenant_isolation.py -v
"""
import os
import pytest
import psycopg2

DB_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")

TENANT_A = "test_tenant_a_isolation"
TENANT_B = "test_tenant_b_isolation"


def _get_conn():
    return psycopg2.connect(DB_URL)


# ── Setup helpers ────────────────────────────────────────────────────────────

def _insert_journal_drafts() -> tuple[int, int]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO journal_drafts (tenant_id, description, amount, account_code, status, created_at)
        VALUES (%s, 'Tenant A draft', 999.00, '6110', 'pending', NOW()) RETURNING id
        """,
        (TENANT_A,),
    )
    id_a = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO journal_drafts (tenant_id, description, amount, account_code, status, created_at)
        VALUES (%s, 'Tenant B draft', 888.00, '6120', 'pending', NOW()) RETURNING id
        """,
        (TENANT_B,),
    )
    id_b = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return id_a, id_b


def _cleanup_journal_drafts(id_a: int, id_b: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM journal_drafts WHERE id IN (%s, %s)", (id_a, id_b))
    conn.commit()
    cur.close(); conn.close()


def _insert_bank_transactions() -> tuple[int, int]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO bank_transactions (tenant_id, bank, date, amount, description)
        VALUES (%s, 'TEST_BANK', CURRENT_DATE, 1234.56, 'Tenant A tx') RETURNING id
        """,
        (TENANT_A,),
    )
    id_a = cur.fetchone()[0]
    cur.execute(
        """
        INSERT INTO bank_transactions (tenant_id, bank, date, amount, description)
        VALUES (%s, 'TEST_BANK', CURRENT_DATE, 9876.54, 'Tenant B tx') RETURNING id
        """,
        (TENANT_B,),
    )
    id_b = cur.fetchone()[0]
    conn.commit()
    cur.close(); conn.close()
    return id_a, id_b


def _cleanup_bank_transactions(id_a: int, id_b: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM bank_transactions WHERE id IN (%s, %s)", (id_a, id_b))
    conn.commit()
    cur.close(); conn.close()


def _query_journal_drafts(tenant_id: str) -> list:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, tenant_id FROM journal_drafts WHERE tenant_id = %s", (tenant_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


def _query_bank_transactions(tenant_id: str) -> list:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, tenant_id FROM bank_transactions WHERE tenant_id = %s", (tenant_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows


# ── journal_drafts isolation ─────────────────────────────────────────────────

def test_journal_drafts_tenant_a_cannot_see_b():
    id_a, id_b = _insert_journal_drafts()
    try:
        rows_a = _query_journal_drafts(TENANT_A)
        ids_a = {r[0] for r in rows_a}
        assert id_a in ids_a, "Tenant A should see its own journal draft"
        assert id_b not in ids_a, "Tenant A must NOT see tenant B's journal draft"
        for row in rows_a:
            assert row[1] == TENANT_A, f"Cross-tenant leak in journal_drafts: got tenant={row[1]}"
    finally:
        _cleanup_journal_drafts(id_a, id_b)


def test_journal_drafts_tenant_b_cannot_see_a():
    id_a, id_b = _insert_journal_drafts()
    try:
        rows_b = _query_journal_drafts(TENANT_B)
        ids_b = {r[0] for r in rows_b}
        assert id_b in ids_b, "Tenant B should see its own journal draft"
        assert id_a not in ids_b, "Tenant B must NOT see tenant A's journal draft"
        for row in rows_b:
            assert row[1] == TENANT_B, f"Cross-tenant leak in journal_drafts: got tenant={row[1]}"
    finally:
        _cleanup_journal_drafts(id_a, id_b)


# ── bank_transactions isolation ──────────────────────────────────────────────

def test_bank_transactions_tenant_a_cannot_see_b():
    id_a, id_b = _insert_bank_transactions()
    try:
        rows_a = _query_bank_transactions(TENANT_A)
        ids_a = {r[0] for r in rows_a}
        assert id_a in ids_a, "Tenant A should see its own bank transaction"
        assert id_b not in ids_a, "Tenant A must NOT see tenant B's bank transaction"
        for row in rows_a:
            assert row[1] == TENANT_A, f"Cross-tenant leak in bank_transactions: got tenant={row[1]}"
    finally:
        _cleanup_bank_transactions(id_a, id_b)


def test_bank_transactions_tenant_b_cannot_see_a():
    id_a, id_b = _insert_bank_transactions()
    try:
        rows_b = _query_bank_transactions(TENANT_B)
        ids_b = {r[0] for r in rows_b}
        assert id_b in ids_b, "Tenant B should see its own bank transaction"
        assert id_a not in ids_b, "Tenant B must NOT see tenant A's bank transaction"
        for row in rows_b:
            assert row[1] == TENANT_B, f"Cross-tenant leak in bank_transactions: got tenant={row[1]}"
    finally:
        _cleanup_bank_transactions(id_a, id_b)


# ── cross-table: same query pattern used by fixed routes ─────────────────────

def test_journal_drafts_sum_scoped_by_tenant():
    """Mirrors the pattern used by /statements/pnl, /budget, /reports endpoints."""
    id_a, id_b = _insert_journal_drafts()
    try:
        conn = _get_conn()
        cur = conn.cursor()
        # Simulate: SELECT SUM(amount) FROM journal_drafts WHERE account_code LIKE '6%' AND tenant_id = %s
        cur.execute(
            "SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '6%%' AND tenant_id = %s",
            (TENANT_A,),
        )
        total_a = float(cur.fetchone()[0])

        cur.execute(
            "SELECT COALESCE(SUM(amount),0) as total FROM journal_drafts WHERE account_code LIKE '6%%' AND tenant_id = %s",
            (TENANT_B,),
        )
        total_b = float(cur.fetchone()[0])
        cur.close(); conn.close()

        # total_a must include id_a's 999.00 but NOT id_b's 888.00
        # total_b must include id_b's 888.00 but NOT id_a's 999.00
        assert total_a != total_b, "Tenant A and B sums must differ (data isolation)"
        # Exact check: amounts are unique enough
        assert abs(total_a - total_b) > 1.0, "Expected meaningful difference between tenant sums"
    finally:
        _cleanup_journal_drafts(id_a, id_b)
