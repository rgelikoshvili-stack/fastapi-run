"""
tests/integration/test_approval_race_condition.py
Verifies that concurrent approve calls on the same draft produce exactly one success.
Requires DATABASE_URL env var and a live DB.
"""
import os
import concurrent.futures
import pytest
import psycopg2
from psycopg2.extras import RealDictCursor

DB_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")


def _get_conn():
    return psycopg2.connect(DB_URL)


def _create_test_draft(tenant_id="test_race") -> int:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO journal_drafts
            (tenant_id, description, amount, account_code, status, created_at)
        VALUES (%s, 'Race condition test', 100.00, '7510', 'pending', NOW())
        RETURNING id
        """,
        (tenant_id,),
    )
    draft_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return draft_id


def _delete_test_draft(draft_id: int):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM journal_drafts WHERE id = %s", (draft_id,))
    conn.commit()
    cur.close()
    conn.close()


def _try_approve(draft_id: int, tenant_id: str) -> str:
    """Attempt to approve using the same SELECT FOR UPDATE pattern as the service."""
    conn = _get_conn()
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(
            "SELECT * FROM journal_drafts WHERE id = %s AND tenant_id = %s FOR UPDATE",
            (draft_id, tenant_id),
        )
        draft = cur.fetchone()
        if not draft:
            return "not_found"
        if draft["status"] != "pending":
            return f"wrong_status:{draft['status']}"
        cur.execute(
            "UPDATE journal_drafts SET status = 'approved' WHERE id = %s",
            (draft_id,),
        )
        conn.commit()
        return "approved"
    except Exception as e:
        conn.rollback()
        return f"error:{e}"
    finally:
        cur.close()
        conn.close()


def test_concurrent_approve_only_one_succeeds():
    draft_id = _create_test_draft()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(_try_approve, draft_id, "test_race") for _ in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        approved_count = results.count("approved")
        assert approved_count == 1, (
            f"Expected exactly 1 approve, got {approved_count}. Results: {results}"
        )
    finally:
        _delete_test_draft(draft_id)
