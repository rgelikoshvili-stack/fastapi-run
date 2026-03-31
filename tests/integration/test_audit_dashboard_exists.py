from pathlib import Path


def test_audit_dashboard_exists():
    path = Path("static/audit_dashboard.html")
    assert path.exists()