"""Static safety contracts for the RS.ge waybill sync UI."""

from pathlib import Path


UI_PATH = Path(__file__).parents[2] / "static" / "rsge-sync.html"


def _ui_source() -> str:
    return UI_PATH.read_text(encoding="utf-8")


def _sync_function(source: str) -> str:
    start = source.index("async function liveSync()")
    end = source.index("\nfunction showToast", start)
    return source[start:end]


def test_sync_button_has_visible_side_effect_warning():
    source = _ui_source()
    button = source.index('id="btnLiveSync"')
    warning = source.index(
        "This action may contact RS.ge and save local sync records."
    )

    assert warning > button
    assert 'class="sync-safety-warning" role="alert"' in source
    assert ".sync-safety-warning" in source


def test_sync_requires_explicit_confirmation_before_post():
    function = _sync_function(_ui_source())

    confirm_at = function.index("window.confirm(")
    cancel_guard_at = function.index("if (!confirmed) return;")
    post_at = function.index("fetch('/rs-ge/sync'")
    assert confirm_at < cancel_guard_at < post_at
    assert "Continue with sync?" in function


def test_settings_sync_also_confirms_before_post_and_records_operator_confirmation():
    source = _ui_source()
    start = source.index("async function runWaybillSync()")
    end = source.index("\nasync function loadSettingsTab", start)
    function = source[start:end]

    confirm_at = function.index("window.confirm(")
    cancel_guard_at = function.index("if(!confirmed)return;")
    post_at = function.index("fetch(BASE+'/rs-ge/sync'")
    assert confirm_at < cancel_guard_at < post_at
    assert "operator_confirmed:true" in function
    button = source.index('id="btnRsgeSync"')
    warning = source.index("This action may contact RS.ge and save local sync records.", button)
    assert warning > button


def test_side_effect_button_is_labeled_sync_not_ping():
    source = _ui_source()
    button_start = source.index('id="btnLiveSync"')
    button_end = source.index("</button>", button_start)
    button_markup = source[button_start:button_end]

    assert "Sync RS.ge waybills" in button_markup
    assert "ping" not in button_markup.lower()


def test_page_load_does_not_start_rsge_sync():
    source = _ui_source()
    init_start = source.index("// Set default dates: current month")
    sync_start = source.index("// ── LIVE RS.ge SOAP SYNC", init_start)
    page_init = source[init_start:sync_start]

    assert "loadWaybills();" in page_init
    assert "liveSync(" not in page_init
