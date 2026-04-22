"""
tests/integration/test_cross_tenant_isolation.py  — Day 15

Two companies sign up via /auth/signup.
Each company's drafts, counterparties, and processed_documents must be invisible
to the other company's token.

Skip: DATABASE_URL not set (CI skips automatically; run locally with real DB).
"""
import os
import time
import pytest
import psycopg2
import requests

BASE_URL = os.environ.get("TEST_BASE_URL", "http://localhost:8080")
DB_URL = os.environ.get("DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="DATABASE_URL not set — skip cross-tenant API tests",
)

# ── Unique company data per test run ─────────────────────────────────────────

_TS = str(int(time.time()))[-8:]  # 8 decimal digits, unique per run

COMPANY_A = {
    "company_type": "legal_entity",
    "company_inn": f"9{_TS}",        # 9 digits
    "company_name_legal": f"Test Company Alpha {_TS}",
    "is_vat_payer": True,
    "email": f"alpha_{_TS}@test.ge",
    "password": "TestPass2026!",
}
COMPANY_B = {
    "company_type": "legal_entity",
    "company_inn": f"8{_TS}",        # 9 digits, different first digit
    "company_name_legal": f"Test Company Beta {_TS}",
    "is_vat_payer": False,
    "email": f"beta_{_TS}@test.ge",
    "password": "TestPass2026!",
}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def two_tenants():
    """Register two companies, return (token_a, tenant_a, token_b, tenant_b).
    Cleans up DB rows after the module finishes.
    """
    resp_a = requests.post(f"{BASE_URL}/auth/signup", json=COMPANY_A, timeout=15)
    assert resp_a.status_code == 200, f"Signup A failed: {resp_a.text}"
    data_a = resp_a.json()["data"]
    token_a = data_a["access_token"]
    tenant_a = data_a["tenant_id"]

    resp_b = requests.post(f"{BASE_URL}/auth/signup", json=COMPANY_B, timeout=15)
    assert resp_b.status_code == 200, f"Signup B failed: {resp_b.text}"
    data_b = resp_b.json()["data"]
    token_b = data_b["access_token"]
    tenant_b = data_b["tenant_id"]

    yield token_a, tenant_a, token_b, tenant_b

    # Cleanup
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    for tid in (tenant_a, tenant_b):
        cur.execute("DELETE FROM journal_drafts WHERE tenant_id = %s", (tid,))
        cur.execute("DELETE FROM counterparties WHERE tenant_id = %s", (tid,))
        cur.execute("DELETE FROM processed_documents WHERE tenant_id = %s", (tid,))
        cur.execute("DELETE FROM users WHERE tenant_id = %s", (tid,))
        cur.execute("DELETE FROM tenants WHERE tenant_id = %s", (tid,))
    conn.commit()
    cur.close()
    conn.close()


@pytest.fixture(scope="module")
def draft_in_tenant_a(two_tenants):
    """Insert a draft directly into DB for tenant A, return its id."""
    _, tenant_a, _, _ = two_tenants
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO journal_drafts
            (tenant_id, description, amount, account_code, status, created_at)
        VALUES (%s, 'Cross-tenant test draft A', 1234.56, '6110', 'pending_approval', NOW())
        RETURNING id
        """,
        (tenant_a,),
    )
    draft_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    yield draft_id
    # Cleanup handled by two_tenants fixture (deletes all drafts for tenant_a)


# ── Tests ─────────────────────────────────────────────────────────────────────

def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_signup_creates_distinct_tenants(two_tenants):
    """Both signups succeed and produce different tenant IDs."""
    _, tenant_a, _, tenant_b = two_tenants
    assert tenant_a != tenant_b, "Each signup must create a unique tenant"
    assert tenant_a.startswith("t_"), f"Expected t_... format, got {tenant_a}"
    assert tenant_b.startswith("t_"), f"Expected t_... format, got {tenant_b}"


def test_tenant_a_auth_me_shows_own_company(two_tenants):
    """/auth/me for tenant A returns company A data."""
    token_a, tenant_a, _, _ = two_tenants
    resp = requests.get(f"{BASE_URL}/auth/me", headers=_auth_header(token_a), timeout=10)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["tenant_id"] == tenant_a
    assert data["company_inn"] == COMPANY_A["company_inn"]


def _queue_draft_ids(token: str) -> set:
    """Return set of draft IDs from /approval/queue for the given token."""
    resp = requests.get(
        f"{BASE_URL}/approval/queue",
        headers=_auth_header(token),
        timeout=10,
    )
    assert resp.status_code == 200, f"Queue request failed: {resp.text}"
    data = resp.json().get("data", {})
    # Response key is "queue" (not "drafts")
    items = data.get("queue", data.get("drafts", []))
    return {d["id"] for d in items}


def test_tenant_b_cannot_see_tenant_a_draft_in_queue(two_tenants, draft_in_tenant_a):
    """Tenant B's approval queue must NOT contain tenant A's draft."""
    _, _, token_b, _ = two_tenants
    draft_ids = _queue_draft_ids(token_b)
    assert draft_in_tenant_a not in draft_ids, (
        f"Tenant B can see tenant A's draft #{draft_in_tenant_a} — RLS breach!"
    )


def test_tenant_a_can_see_own_draft(two_tenants, draft_in_tenant_a):
    """Tenant A's approval queue must contain its own draft."""
    token_a, _, _, _ = two_tenants
    draft_ids = _queue_draft_ids(token_a)
    assert draft_in_tenant_a in draft_ids, (
        f"Tenant A cannot see its own draft #{draft_in_tenant_a} — WHERE clause broken!"
    )


def test_rls_enforcement_via_guc(two_tenants, draft_in_tenant_a):
    """Direct DB test: setting GUC to tenant B must hide tenant A's draft."""
    _, tenant_a, _, tenant_b = two_tenants
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    # GUC = tenant_b → must NOT see tenant_a's draft
    cur.execute("SELECT set_config('app.current_tenant_id', %s, false)", (tenant_b,))
    cur.execute("SELECT id FROM journal_drafts WHERE id = %s", (draft_in_tenant_a,))
    row = cur.fetchone()
    assert row is None, f"RLS failed: tenant B sees draft #{draft_in_tenant_a} via GUC"

    # GUC = tenant_a → MUST see it
    cur.execute("SELECT set_config('app.current_tenant_id', %s, false)", (tenant_a,))
    cur.execute("SELECT id FROM journal_drafts WHERE id = %s", (draft_in_tenant_a,))
    row = cur.fetchone()
    assert row is not None, f"Tenant A cannot see own draft via GUC — RLS too strict?"

    # GUC = '' (reset) → pass-through, sees all
    cur.execute("SELECT set_config('app.current_tenant_id', '', false)")
    cur.execute("SELECT id FROM journal_drafts WHERE id = %s", (draft_in_tenant_a,))
    row = cur.fetchone()
    assert row is not None, "Pass-through mode (GUC='') must see all rows"

    cur.close()
    conn.close()


def test_tenant_b_counterparties_empty_of_tenant_a_data(two_tenants):
    """Counterparties endpoint returns only own data."""
    _, tenant_a, token_b, tenant_b = two_tenants

    # Insert a counterparty for tenant A
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO counterparties (tenant_id, inn, name, type, total_transactions)
        VALUES (%s, '999888777', 'Secret Company A', 'vendor', 1)
        ON CONFLICT (tenant_id, inn) DO NOTHING
        """,
        (tenant_a,),
    )
    conn.commit()
    cur.close()
    conn.close()

    # Tenant B should not see it
    resp = requests.get(
        f"{BASE_URL}/crm/counterparties",
        headers=_auth_header(token_b),
        timeout=10,
    )
    if resp.status_code == 404:
        pytest.skip("CRM counterparties endpoint not available")
    assert resp.status_code == 200
    items = resp.json().get("data", [])
    inns = [item.get("inn") for item in (items if isinstance(items, list) else [])]
    assert "999888777" not in inns, "Tenant B can see tenant A's counterparty — isolation breach!"
