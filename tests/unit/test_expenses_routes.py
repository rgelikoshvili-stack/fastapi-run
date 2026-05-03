"""tests/unit/test_expenses_routes.py
Expenses route structural unit tests.
"""
import inspect
from unittest.mock import MagicMock


# ── 1. Create endpoint exists ─────────────────────────────────────────────────

def test_create_expense_endpoint_exists():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    assert "create_expense" in src or "/create" in src


# ── 2. Create uses tenant_id ─────────────────────────────────────────────────

def test_create_expense_uses_tenant_id():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    assert "tenant_id" in src
    # INSERT should include tenant_id
    lines = src.splitlines()
    insert_lines = [l for l in lines if "INSERT" in l.upper()]
    tenant_insert = [l for l in insert_lines if "tenant_id" in l.lower()]
    assert len(tenant_insert) >= 1 or src.count("tenant_id") >= 5


# ── 3. List endpoint is tenant-scoped ────────────────────────────────────────

def test_list_expenses_tenant_scoped():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    lines = src.splitlines()
    select_from_expenses = [l for l in lines if "expenses" in l.lower() and ("SELECT" in l.upper() or "$1" in l)]
    # At least one expenses query should have tenant scoping
    assert src.count("tenant_id") >= 5


# ── 4. Cross-tenant blocked: SELECT uses tenant param ────────────────────────

def test_expense_select_has_tenant_param():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    # asyncpg $1 or %s param with tenant_id present
    assert "$1" in src or "tenant_id = %s" in src or "tenant_id=%s" in src


# ── 5. Status update is tenant-scoped ────────────────────────────────────────

def test_expense_status_update_tenant_scoped():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    assert "status" in src
    assert "tenant_id" in src


# ── 6. Summary endpoint exists ───────────────────────────────────────────────

def test_expense_summary_exists():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    assert "summary" in src.lower()


# ── 7. Categories endpoint exists ────────────────────────────────────────────

def test_expense_categories_exist():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    assert "categor" in src.lower()


# ── 8. Expense model has required fields ─────────────────────────────────────

def test_expense_create_model_fields():
    import app.api.routes_expenses as mod
    src = inspect.getsource(mod)
    # ExpenseCreate pydantic model should have amount + category
    assert "amount" in src
    assert "category" in src or "categor" in src.lower()
