import inspect
from datetime import date


# ── Period closing account ─────────────────────────────────────────────────

def test_closing_entry_uses_account_4210():
    """Period closing must write to 4210 (Retained Earnings), not 3600."""
    import app.api.routes_closing as mod
    assert mod.RETAINED_EARNINGS == "4210", (
        f"RETAINED_EARNINGS must be '4210' but got '{mod.RETAINED_EARNINGS}'. "
        "Account 3600 is not in the Georgian COA; closing entries would disappear from Balance Sheet."
    )


def test_closing_uses_posted_status_only():
    """Closing queries must only aggregate posted drafts."""
    import app.api.routes_closing as mod
    src = inspect.getsource(mod)
    assert "status = 'posted'" in src, "Closing queries must filter status = 'posted'"
    assert "auto_approved" not in src, "Closing queries must not include auto_approved drafts"


# ── Ledger posted-only ─────────────────────────────────────────────────────

def test_ledger_service_uses_posted_only():
    """Ledger and trial balance must not expose pending/approved drafts."""
    import app.api.services.ledger_service as mod
    src = inspect.getsource(mod)
    assert "status = 'posted'" in src, "ledger_service must filter status = 'posted'"
    assert "auto_approved" not in src, "ledger_service must not include auto_approved drafts"


# ── Posting period lock helper ─────────────────────────────────────────────

def test_posting_period_lock_helper_detects_locked_month():
    from app.api.services.posting_service import _is_period_locked_sync

    class Cur:
        def __init__(self):
            self.params = None

        def execute(self, sql, params):
            self.sql = sql
            self.params = params

        def fetchone(self):
            return {"exists": 1}

    cur = Cur()
    assert _is_period_locked_sync(cur, "tenant-a", date(2026, 5, 4)) is True
    assert cur.params == ("tenant-a", 2026, 5)


def test_posting_period_lock_helper_allows_unlocked_month():
    from app.api.services.posting_service import _is_period_locked_sync

    class Cur:
        def execute(self, sql, params):
            self.params = params

        def fetchone(self):
            return None

    assert _is_period_locked_sync(Cur(), "tenant-a", "2026-05-04") is False
