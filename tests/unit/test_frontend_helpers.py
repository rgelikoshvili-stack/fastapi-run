from pathlib import Path


ROOT = Path("static")


def test_frontend_helper_files_export_expected_globals():
    api = (ROOT / "js" / "core" / "api.js").read_text(encoding="utf-8")
    modal = (ROOT / "js" / "core" / "modal.js").read_text(encoding="utf-8")
    toast = (ROOT / "js" / "core" / "toast.js").read_text(encoding="utf-8")
    debounce = (ROOT / "js" / "core" / "debounce.js").read_text(encoding="utf-8")

    assert "window.BHApi" in api
    assert "window.BHModal" in modal
    assert "window.BHToast" in toast
    assert "window.BHDebounce" in debounce


def test_approval_page_loads_frontend_helpers():
    approval = (ROOT / "approval.html").read_text(encoding="utf-8")
    for name in (
        "core/api.js",
        "core/modal.js",
        "core/toast.js",
        "core/debounce.js",
    ):
        assert name in approval


def test_payroll_page_loads_frontend_helpers():
    payroll = (ROOT / "payroll_ledger.html").read_text(encoding="utf-8")
    for name in (
        "/static/js/core/api.js",
        "/static/js/core/modal.js",
        "/static/js/core/toast.js",
        "/static/js/core/debounce.js",
    ):
        assert name in payroll
    assert "errorBox" in payroll
    assert "apiRequest(url)" in payroll


def test_shadow_preview_disables_confirm_when_preview_missing():
    shadow = (ROOT / "js" / "pages" / "shadow_posting.js").read_text(encoding="utf-8")
    assert "const canConfirm = !!p;" in shadow
    assert "disabled aria-disabled=\"true\"" in shadow


def test_approval_page_uses_debounced_search_and_confirmation_modals():
    approval = (ROOT / "approval.html").read_text(encoding="utf-8")
    assert "pendingSearchChanged()" in approval
    assert "pendingRequestSeq" in approval
    assert "bulk-approve-confirm" in approval
    assert "autopilot-confirm" in approval


def test_reporting_and_trade_hubs_exist():
    reports = (ROOT / "reports.html").read_text(encoding="utf-8")
    trade = (ROOT / "purchases_sales.html").read_text(encoding="utf-8")
    sidebar = (ROOT / "components" / "sidebar.html").read_text(encoding="utf-8")

    assert "Reporting Workbench" in reports
    assert "/static/financial_reports.html" in reports
    assert "/static/purchases_sales.html" in reports
    assert "Purchases & Sales Workbench" in trade
    assert "/inventory/purchase-orders" in trade
    assert "/invoices/list" in trade
    assert "/static/purchases_sales.html" in sidebar
    assert "/static/reports.html" in sidebar
