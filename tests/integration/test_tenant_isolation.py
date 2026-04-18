"""
tests/integration/test_tenant_isolation.py
Verifies that tenant A cannot read tenant B's data via the API.
Requires DATABASE_URL + a running server at TEST_BASE_URL (default: http://localhost:8000).
"""
import os
import pytest
import psycopg2

DB_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")

TENANT_A = "test_tenant_a"
TENANT_B = "test_tenant_b"


def _get_conn():
    return psycopg2.connect(DB_URL)


def _setup_test_data() -> tuple[int, int]:
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
    cur.close()
    conn.close()
    return id_a, id_b


def _cleanup(id_a: int, id_b: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM journal_drafts WHERE id IN (%s, %s)", (id_a, id_b))
    conn.commit()
    cur.close()
    conn.close()


def _query_drafts(tenant_id: str) -> list:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, tenant_id FROM journal_drafts WHERE tenant_id = %s",
        (tenant_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def test_tenant_a_cannot_see_tenant_b_data():
    id_a, id_b = _setup_test_data()
    try:
        rows_a = _query_drafts(TENANT_A)
        ids_a = {r[0] for r in rows_a}

        assert id_a in ids_a, "Tenant A should see its own draft"
        assert id_b not in ids_a, "Tenant A must NOT see tenant B's draft"

        for row in rows_a:
            assert row[1] == TENANT_A, f"Cross-tenant leak: row tenant={row[1]} in tenant A query"
    finally:
        _cleanup(id_a, id_b)


def test_tenant_b_cannot_see_tenant_a_data():
    id_a, id_b = _setup_test_data()
    try:
        rows_b = _query_drafts(TENANT_B)
        ids_b = {r[0] for r in rows_b}

        assert id_b in ids_b, "Tenant B should see its own draft"
        assert id_a not in ids_b, "Tenant B must NOT see tenant A's draft"

        for row in rows_b:
            assert row[1] == TENANT_B, f"Cross-tenant leak: row tenant={row[1]} in tenant B query"
    finally:
        _cleanup(id_a, id_b)
