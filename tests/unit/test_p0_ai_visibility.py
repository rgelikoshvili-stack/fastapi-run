"""tests/unit/test_p0_ai_visibility.py
P0-5: AI tool registry must have read-only access to:
  - waybills, tax_invoices, commercial_invoices
  - triangle_matches
  - evidence_bundles
  - accounting risk summary (period lock, FX, etc.)

All tests mock the DB — no real connection needed.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def run_sync(coro):
    return asyncio.run(coro)


def _fake_conn(rows_by_table: dict):
    """Build a mock asyncpg connection where fetch returns rows by table keyword."""
    conn = AsyncMock()

    async def _fetch(query, *args, **kwargs):
        q = str(query).lower()
        for table, rows in rows_by_table.items():
            if table in q:
                return rows
        return []

    async def _fetchrow(query, *args, **kwargs):
        q = str(query).lower()
        for table, rows in rows_by_table.items():
            if table in q and rows:
                return rows[0]
        return None

    async def _fetchval(query, *args, **kwargs):
        q = str(query).lower()
        for table, val in rows_by_table.items():
            if table in q and isinstance(val, (int, float)):
                return val
        return 0

    conn.fetch = _fetch
    conn.fetchrow = _fetchrow
    conn.fetchval = _fetchval
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _row(**kwargs):
    """Create a dict-like row mock."""
    class _Row(dict):
        def __getitem__(self, k):
            return super().__getitem__(k)
    return _Row(kwargs)


# ── search_documents includes waybills ────────────────────────────────────────

def test_search_finds_waybills():
    waybill_row = _row(id=1, description="WB-2026-001", partner="Vendor A",
                       amount=1000.0, status="imported", source_table="waybill")
    ctx = _fake_conn({"waybills": [waybill_row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _search_documents
        result = run_sync(_search_documents({"query": "Vendor"}, "tenant1"))
    assert result["total_found"] >= 1
    tables = [r.get("source_table") for r in result["results"]]
    assert "waybill" in tables


def test_search_finds_tax_invoices():
    row = _row(id=2, description="SFP-001", partner="Corp B",
               amount=800.0, status="imported", source_table="tax_invoice")
    ctx = _fake_conn({"tax_invoices": [row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _search_documents
        result = run_sync(_search_documents({"query": "Corp"}, "tenant1"))
    tables = [r.get("source_table") for r in result["results"]]
    assert "tax_invoice" in tables


def test_search_finds_commercial_invoices():
    row = _row(id=3, description="CI-100", partner="Importer X",
               amount=500.0, status="imported", source_table="commercial_invoice")
    ctx = _fake_conn({"commercial_invoices": [row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _search_documents
        result = run_sync(_search_documents({"query": "Importer"}, "tenant1"))
    tables = [r.get("source_table") for r in result["results"]]
    assert "commercial_invoice" in tables


def test_search_finds_evidence_bundles():
    row = _row(id="uuid-1", description="journal_draft", partner="draft-42",
               amount=0.95, status="ready", source_table="evidence_bundle")
    ctx = _fake_conn({"evidence_bundles": [row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _search_documents
        result = run_sync(_search_documents({"query": "draft-42"}, "tenant1"))
    tables = [r.get("source_table") for r in result["results"]]
    assert "evidence_bundle" in tables


def test_search_requires_query():
    from app.api.services.ai_tool_registry import _search_documents
    ctx = _fake_conn({})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        result = run_sync(_search_documents({}, "tenant1"))
    assert "error" in result


# ── get_rsge_document_status ─────────────────────────────────────────────────

def test_get_rsge_document_status_finds_waybill():
    row = _row(id=10, waybill_number="WB-001", waybill_date="2026-08-10",
               seller_name="Vendor", buyer_name="Us", total_amount=1000.0,
               vat_amount=180.0, status="imported", version=1)
    ctx = _fake_conn({"waybills": [row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_rsge_document_status
        result = run_sync(_get_rsge_document_status({"document_number": "WB-001"}, "tenant1"))
    assert result["found"] is True
    assert any(d.get("source_table") == "waybill" for d in result["documents"])


def test_get_rsge_document_status_not_found():
    ctx = _fake_conn({"waybills": [], "tax_invoices": []})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_rsge_document_status
        result = run_sync(_get_rsge_document_status({"document_number": "NONE-999"}, "tenant1"))
    assert result["found"] is False


def test_get_rsge_document_status_requires_number():
    ctx = _fake_conn({})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_rsge_document_status
        result = run_sync(_get_rsge_document_status({}, "tenant1"))
    assert "error" in result


def test_get_rsge_document_status_never_returns_secrets():
    """Result must not contain password, api_key, token, or secret fields."""
    row = _row(id=1, waybill_number="WB-X", waybill_date="2026-01-01",
               seller_name="Corp", buyer_name="Us", total_amount=100.0,
               vat_amount=18.0, status="imported", version=1)
    ctx = _fake_conn({"waybills": [row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_rsge_document_status
        result = run_sync(_get_rsge_document_status({"document_number": "WB-X"}, "tenant1"))
    result_str = str(result).lower()
    for forbidden in ["password", "api_key", "token", "secret", "vault_key"]:
        assert forbidden not in result_str


# ── get_triangle_match_status ─────────────────────────────────────────────────

def test_get_triangle_match_status_returns_matches():
    row = _row(id=1, match_score=0.75, match_status="partial",
               mismatch_fields=["amount"], waybill_total=1000.0,
               tax_invoice_total=1100.0, commercial_invoice_total=None,
               amount_diff=100.0, journal_draft_id=5, matched_at="2026-08-10",
               waybill_number="WB-001", seller_name="Corp", invoice_number="SFP-001")
    ctx = _fake_conn({"triangle_matches": [row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_triangle_match_status
        result = run_sync(_get_triangle_match_status({}, "tenant1"))
    assert result["count"] >= 1
    match = result["matches"][0]
    assert match.get("risk_level") in ("LOW", "MEDIUM", "HIGH")


def test_get_triangle_match_status_high_risk_for_mismatch():
    row = _row(id=1, match_score=0.2, match_status="mismatch",
               mismatch_fields=["seller_inn", "amount"],
               waybill_total=1000.0, tax_invoice_total=500.0,
               commercial_invoice_total=None, amount_diff=500.0,
               journal_draft_id=None, matched_at="2026-08-10",
               waybill_number="WB-BAD", seller_name="Corp", invoice_number="SFP-BAD")
    ctx = _fake_conn({"triangle_matches": [row]})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_triangle_match_status
        result = run_sync(_get_triangle_match_status({}, "tenant1"))
    assert result["matches"][0]["risk_level"] == "HIGH"


# ── get_accounting_risk_summary ───────────────────────────────────────────────

def test_get_accounting_risk_summary_structure():
    ctx = _fake_conn({"waybills": 0, "triangle_matches": 0, "currency_rates": 5,
                      "period_locks": None, "journal_drafts": 0})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_accounting_risk_summary
        result = run_sync(_get_accounting_risk_summary({}, "tenant1"))
    assert "risk_count" in result
    assert "risks" in result
    assert "summary" in result
    assert result.get("approval_required") is False


def test_get_accounting_risk_summary_never_exposes_secrets():
    ctx = _fake_conn({})
    with patch("app.api.services.ai_tool_registry.get_conn", return_value=ctx):
        from app.api.services.ai_tool_registry import _get_accounting_risk_summary
        result = run_sync(_get_accounting_risk_summary({}, "tenant1"))
    result_str = str(result).lower()
    for forbidden in ["password", "api_key", "token", "vault_key", "secret"]:
        assert forbidden not in result_str


# ── Tool registry completeness ────────────────────────────────────────────────

def test_tool_registry_includes_new_p0_5_tools():
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS, _TOOL_MAP
    required = [
        "get_rsge_document_status",
        "get_triangle_match_status",
        "get_accounting_risk_summary",
    ]
    for tool in required:
        assert tool in TOOL_DESCRIPTIONS, f"Missing tool description: {tool}"
        assert tool in _TOOL_MAP, f"Missing tool implementation: {tool}"


def test_all_tools_are_read_only_or_approval_required():
    """No tool in the registry may execute direct DB writes without approval_required=True."""
    # This is a documentation/contract test — verifies the expected behavior
    from app.api.services.ai_tool_registry import TOOL_DESCRIPTIONS
    write_tools = {"prepare_approval_preview", "prepare_posting_preview"}
    for name, desc in TOOL_DESCRIPTIONS.items():
        if name in write_tools:
            # These return approval_required=True — they don't execute
            continue
        # All other tools should be read-only (no direct DB mutations)
        assert "delete" not in desc.lower()
        assert "write" not in desc.lower()
        assert "insert" not in desc.lower()


def test_ai_tools_cannot_call_rsge_mutations():
    """Verify that no tool dispatches to RS.ge mutation endpoints."""
    import inspect
    from app.api.services import ai_tool_registry
    src = inspect.getsource(ai_tool_registry)
    # No live RS.ge action calls should appear in the tool code
    for forbidden in ["rsge_submission_service", "call_rsge", "post_to_rsge",
                      "activate_waybill", "confirm_invoice"]:
        assert forbidden not in src, f"AI tool registry must not call RS.ge: {forbidden}"


def test_search_documents_is_tenant_scoped():
    """Verify search_documents passes tenant_id to all queries."""
    import inspect
    from app.api.services.ai_tool_registry import _search_documents
    src = inspect.getsource(_search_documents)
    # Every DB query should include tenant_id parameter
    assert "tenant_id" in src
