from pathlib import Path


def test_approval_dashboard_exists():
    path = Path("static/approval_dashboard.html")
    assert path.exists()