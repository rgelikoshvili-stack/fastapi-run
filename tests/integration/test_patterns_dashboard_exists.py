from pathlib import Path


def test_patterns_dashboard_exists():
    path = Path("static/patterns_dashboard.html")
    assert path.exists()