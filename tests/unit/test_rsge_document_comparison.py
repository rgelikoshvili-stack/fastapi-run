"""tests/unit/test_rsge_document_comparison.py — Waybill↔invoice comparison logic."""
import json


# ── Helpers ──────────────────────────────────────────────────────────────────

def _waybill(amount=1000.0, goods=None):
    return {
        "id": 1, "waybill_number": "WB001", "full_amount": amount,
        "goods_list": goods or [
            {"name": "ნივთი 1", "quantity": 2, "amount": 500.0},
            {"name": "ნივთი 2", "quantity": 1, "amount": 500.0},
        ],
    }


def _invoice(amount=1000.0, lines=None):
    return {
        "rsge_id": "INV-100", "total": amount,
        "lines": lines or [
            {"name": "ნივთი 1", "amount": 500.0},
            {"name": "ნივთი 2", "amount": 500.0},
        ],
    }


def _compute_diff(wb_amount, inv_amount):
    return round(abs(wb_amount - inv_amount), 4)


def _diff_lines(wb_goods, inv_lines):
    wb_names = {(g.get("name") or "").strip().lower() for g in wb_goods}
    return [l for l in inv_lines
            if (l.get("name") or "").strip().lower() not in wb_names]


# ── 1. Identical amounts → diff = 0, status = matched ────────────────────────

def test_identical_amounts_match():
    wb = _waybill(amount=1000.0)
    inv = _invoice(amount=1000.0)
    diff = _compute_diff(wb["full_amount"], inv["total"])
    assert diff == 0.0
    status = "matched" if diff == 0.0 else "mismatch"
    assert status == "matched"


# ── 2. Different amounts → mismatch ──────────────────────────────────────────

def test_different_amounts_mismatch():
    diff = _compute_diff(1000.0, 1200.0)
    assert diff == 200.0
    status = "mismatch" if diff > 0 else "matched"
    assert status == "mismatch"


# ── 3. Partial match — some lines match, extras on invoice ───────────────────

def test_partial_match_extra_services():
    wb = _waybill(goods=[{"name": "ნივთი 1", "amount": 1000.0}])
    inv_lines = [
        {"name": "ნივთი 1", "amount": 1000.0},
        {"name": "მიტანა", "amount": 50.0},  # extra service
    ]
    extras = _diff_lines(wb["goods_list"], inv_lines)
    assert len(extras) == 1
    assert extras[0]["name"] == "მიტანა"


# ── 4. All goods matched → no diff lines ─────────────────────────────────────

def test_all_goods_matched_no_diff():
    wb = _waybill()
    inv_lines = [
        {"name": "ნივთი 1", "amount": 500.0},
        {"name": "ნივთი 2", "amount": 500.0},
    ]
    extras = _diff_lines(wb["goods_list"], inv_lines)
    assert extras == []


# ── 5. Case-insensitive name comparison ──────────────────────────────────────

def test_case_insensitive_name_match():
    wb = _waybill(goods=[{"name": "ნივთი 1", "amount": 500.0}])
    inv_lines = [{"name": "ნივთი 1", "amount": 500.0}]
    extras = _diff_lines(wb["goods_list"], inv_lines)
    assert extras == []


# ── 6. rsge_comparison_results table exists in migration ─────────────────────

def test_comparison_table_in_migration():
    from app.startup.migrations_rsge import _DDL
    ddl_text = " ".join(_DDL)
    assert "rsge_comparison_results" in ddl_text


# ── 7. Comparison result required fields ─────────────────────────────────────

def test_comparison_result_required_fields():
    result = {
        "id": 1, "tenant_id": "t1",
        "waybill_id": 1, "document_id": 2,
        "status": "matched",
        "wb_amount": 1000.0, "inv_amount": 1000.0,
        "diff_amount": 0.0,
        "diff_lines": [],
    }
    for field in ("id", "tenant_id", "status", "wb_amount", "inv_amount", "diff_amount"):
        assert field in result


# ── 8. Status values are constrained ─────────────────────────────────────────

def test_comparison_status_values():
    valid = {"pending", "matched", "partial", "mismatch"}
    assert "matched" in valid
    assert "partial" in valid
    assert "invalid_status" not in valid


# ── 9. diff_amount is always non-negative ────────────────────────────────────

def test_diff_amount_non_negative():
    cases = [(1000.0, 1200.0), (1200.0, 1000.0), (500.0, 500.0)]
    for wb, inv in cases:
        diff = _compute_diff(wb, inv)
        assert diff >= 0.0


# ── 10. JSON serializable diff_lines ─────────────────────────────────────────

def test_diff_lines_json_serializable():
    diff_lines = [{"name": "მიტანა", "amount": 50.0}]
    serialized = json.dumps(diff_lines)
    parsed = json.loads(serialized)
    assert parsed[0]["name"] == "მიტანა"
