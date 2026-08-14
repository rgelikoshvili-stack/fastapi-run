"""tests/unit/test_rsge_document_status_mapping.py — RS.ge status code → internal status."""


# ── RS.ge invoice status codes (SOAP) ────────────────────────────────────────
# 0 = saved/draft, 1 = confirmed, 2 = rejected, 3 = cancelled, 5 = corrected
_STATUS_MAP = {
    "0":  "saved",
    "1":  "confirmed",
    "2":  "rejected",
    "3":  "cancelled",
    "5":  "corrected",
    "-1": "deleted",
}

# RS.ge waybill statuses
_WB_STATUS_MAP = {
    "0": "saved",
    "1": "active",
    "2": "closed",
    "3": "cancelled",
}


def _map_status(code: str, entity="document") -> str:
    m = _WB_STATUS_MAP if entity == "waybill" else _STATUS_MAP
    return m.get(str(code), "unknown")


# ── 1. Status 0 → saved ───────────────────────────────────────────────────────

def test_status_0_is_saved():
    assert _map_status("0") == "saved"


# ── 2. Status 1 → confirmed ──────────────────────────────────────────────────

def test_status_1_is_confirmed():
    assert _map_status("1") == "confirmed"


# ── 3. Status 2 → rejected ───────────────────────────────────────────────────

def test_status_2_is_rejected():
    assert _map_status("2") == "rejected"


# ── 4. Status 3 → cancelled ──────────────────────────────────────────────────

def test_status_3_is_cancelled():
    assert _map_status("3") == "cancelled"


# ── 5. Status 5 → corrected ──────────────────────────────────────────────────

def test_status_5_is_corrected():
    assert _map_status("5") == "corrected"


# ── 6. Unknown status → unknown ──────────────────────────────────────────────

def test_unknown_status_returns_unknown():
    assert _map_status("999") == "unknown"


# ── 7. Waybill status 1 → active ─────────────────────────────────────────────

def test_waybill_status_1_is_active():
    assert _map_status("1", "waybill") == "active"


# ── 8. Waybill status 3 → cancelled ─────────────────────────────────────────

def test_waybill_status_3_is_cancelled():
    assert _map_status("3", "waybill") == "cancelled"


# ── 9. rsge_status stored in rsge_documents ──────────────────────────────────

def test_rsge_status_field_in_migration():
    from app.startup.migrations_rsge import _DDL
    ddl = " ".join(_DDL)
    assert "rsge_status" in ddl


# ── 10. rsge_status_code also stored ─────────────────────────────────────────

def test_rsge_status_code_field_in_migration():
    from app.startup.migrations_rsge import _DDL
    ddl = " ".join(_DDL)
    assert "rsge_status_code" in ddl


# ── 11. status_code stored as string (not int) in DTO ────────────────────────

def test_status_code_is_string_in_dto():
    from app.api.services.rsge_document_service import _map_invoice_to_dto
    raw = {
        "ID": "1", "INVOICE_NUMBER": "I1", "SELLER_TIN": "1",
        "SELLER_NAME": "S", "BUYER_TIN": "2", "BUYER_NAME": "B",
        "OPERATION_DATE": "2025-01-01", "TOTAL": 100, "VAT": 0,
        "STATUS": 1,  # integer from SOAP
        "STATUS_TXT": "confirmed",
        "OVERHEAD_NO": "",
    }
    dto = _map_invoice_to_dto(raw)
    assert isinstance(dto.status_code, str)


# ── 12. action service warns on wrong status for confirm ────────────────────

def test_action_warning_for_non_saved_confirm():
    from app.api.services.rsge_action_service import _action_warnings
    warnings = _action_warnings("confirm", "confirmed", 100.0)
    assert len(warnings) > 0
