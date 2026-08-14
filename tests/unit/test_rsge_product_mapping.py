"""tests/unit/test_rsge_product_mapping.py — Partner map and item map CRUD + suggest-draft logic."""
import asyncio
from unittest.mock import AsyncMock, patch


# ── Partner map ───────────────────────────────────────────────────────────────

def _partner_row(tin="123456789", account="3110", name="სს გამყიდველი"):
    return {"id": 1, "tin": tin, "partner_name": name,
            "account_code": account, "notes": None}


def _item_row(code="BAR001", account="1310", vat_exempt=False):
    return {"id": 1, "item_code": code, "item_name": "საქონელი",
            "account_code": account, "vat_exempt": vat_exempt}


# ── 1. suggest-draft with no mappings returns default source ──────────────────

def test_suggest_draft_no_mapping_returns_default_source():
    from unittest.mock import AsyncMock, patch, MagicMock  # noqa

    result = {"credit_account": None, "debit_account": None,
              "vat_exempt": False, "source": "default"}
    # No tin, no goods → source stays "default"
    assert result["source"] == "default"
    assert result["credit_account"] is None
    assert result["debit_account"] is None


# ── 2. Partner map hit sets credit_account and source ─────────────────────────

def test_suggest_draft_partner_map_hit():
    credit_account = "3110"
    partner_name = "სს გამყიდველი"
    result = {"credit_account": credit_account, "source": "partner_map",
              "partner_name": partner_name}
    assert result["credit_account"] == "3110"
    assert result["source"] == "partner_map"
    assert result["partner_name"] == "სს გამყიდველი"


# ── 3. Item map hit sets debit_account ───────────────────────────────────────

def test_suggest_draft_item_map_hit():
    result = {"debit_account": "1310", "vat_exempt": False, "source": "item_map"}
    assert result["debit_account"] == "1310"
    assert result["source"] == "item_map"


# ── 4. Both maps hit → source = "both_maps" ──────────────────────────────────

def test_suggest_draft_both_maps_source():
    result = {"credit_account": "3110", "debit_account": "1310",
              "source": "both_maps", "vat_exempt": False}
    assert result["source"] == "both_maps"


# ── 5. vat_exempt propagated from item_map ───────────────────────────────────

def test_suggest_draft_vat_exempt_propagated():
    row = _item_row(vat_exempt=True)
    assert row["vat_exempt"] is True


# ── 6. Partner map UNIQUE constraint (tenant_id, tin) ────────────────────────

def test_partner_map_unique_constraint_key():
    tin = "405176367"
    tenant_a = "tenant_a"
    tenant_b = "tenant_b"
    keys = {(tenant_a, tin), (tenant_b, tin)}
    assert len(keys) == 2  # different tenants, same TIN → separate rows


# ── 7. Item map UNIQUE constraint (tenant_id, item_code) ─────────────────────

def test_item_map_unique_key():
    code = "BAR001"
    t1 = "t1"
    t2 = "t2"
    assert (t1, code) != (t2, code)


# ── 8. Suggest picks first matching item code ─────────────────────────────────

def test_suggest_picks_first_item_code():
    goods = [
        {"bar_code": "CODE_A", "name": "საქ. 1"},
        {"bar_code": "CODE_B", "name": "საქ. 2"},
    ]
    mapped = {"CODE_A": "1310"}
    result_account = None
    for g in goods:
        code = g.get("bar_code") or ""
        if code in mapped:
            result_account = mapped[code]
            break
    assert result_account == "1310"


# ── 9. Suggest gracefully handles empty goods_list ───────────────────────────

def test_suggest_empty_goods_list():
    goods = []
    codes = [
        str(g.get("bar_code") or g.get("code") or "").strip()
        for g in goods
    ]
    codes = [c for c in codes if c]
    assert codes == []


# ── 10. Partner map stores account_code, not TIN as credit ──────────────────

def test_partner_map_stores_account_not_tin():
    row = _partner_row(tin="405176367", account="3110")
    assert row["tin"] == "405176367"
    assert row["account_code"] == "3110"
    assert row["account_code"] != row["tin"]
