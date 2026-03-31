from pathlib import Path

def test_main_dashboard_exists():
    assert Path("static/main_dashboard.html").exists()