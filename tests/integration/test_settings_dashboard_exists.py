from pathlib import Path

def test_settings_dashboard_exists():
    assert Path("static/settings.html").exists()