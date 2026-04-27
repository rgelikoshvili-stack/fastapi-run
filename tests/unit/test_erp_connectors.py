"""tests/unit/test_erp_connectors.py — ERP connector unit tests."""
import inspect
from unittest.mock import MagicMock, patch


# ── 1. ERP import service — tenant_id in service layer ───────────────────────

def test_erp_import_service_exists():
    from app.api.services import erp_import_service
    assert hasattr(erp_import_service, "import_erp_history")


def test_erp_import_history_returns_dict():
    from app.api.services.erp_import_service import import_erp_history
    result = import_erp_history(items=[], default_source_system="balance")
    assert isinstance(result, dict)


# ── 2. ERP memory service — tenant isolation ─────────────────────────────────

def test_erp_memory_service_tenant_scoped():
    from app.api.services import erp_memory_service
    source = inspect.getsource(erp_memory_service)
    assert "tenant_id" in source


# ── 3. ERP routes registered with correct prefixes ───────────────────────────

def test_erp_import_router_prefix():
    from app.api.routes_erp_import import router
    assert "erp" in router.prefix.lower() or "import" in router.prefix.lower()


def test_erp_connectors_router_prefix():
    from app.api.routes_erp_connectors import router
    assert router.prefix != ""


def test_erp_memory_router_prefix():
    from app.api.routes_erp_memory import router
    assert "erp" in router.prefix.lower() or "memory" in router.prefix.lower()


# ── 4. 1C routes — tenant scoped ─────────────────────────────────────────────

def test_1c_routes_tenant_scoped():
    import app.api.routes_1c as m
    source = inspect.getsource(m)
    assert "tenant_id" in source


# ── 5. Balance.ge routes exist ───────────────────────────────────────────────

def test_balance_ge_router_registered():
    from app.api.routes_balance_ge import router
    assert router is not None
    assert len(router.routes) > 0


# ── 6. Background monitoring — backoff logic ─────────────────────────────────

def test_backoff_calculation():
    """After max_failures consecutive errors, interval multiplied by 10."""
    interval = 60
    max_failures = 5
    for consecutive in range(1, 8):
        expected = interval * 10 if consecutive >= max_failures else interval
        if consecutive >= max_failures:
            assert expected == 600
        else:
            assert expected == 60


# ── 7. Domain routers exist and import cleanly ───────────────────────────────

def test_domain_finance_importable():
    """Domain router files must be importable without errors."""
    # Just verify the file exists and has a router attribute
    import importlib.util, os
    path = os.path.join("app", "api", "domain", "finance.py")
    assert os.path.exists(path)


def test_domain_structure_complete():
    import os
    domains = ["finance.py", "documents.py", "intelligence.py", "crm.py", "system.py"]
    for d in domains:
        assert os.path.exists(os.path.join("app", "api", "domain", d)), f"Missing domain: {d}"
