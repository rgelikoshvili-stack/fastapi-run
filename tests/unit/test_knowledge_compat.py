"""Compatibility tests for root bridge_hub_knowledge.py shim."""
import inspect


def test_bridge_hub_knowledge_has_no_import_star():
    import bridge_hub_knowledge as mod
    src = inspect.getsource(mod)
    assert "import *" not in src
    assert "backward-compatibility shim" in src


def test_bridge_hub_knowledge_reexports_public_knowledge_api():
    import bridge_hub_knowledge as legacy
    import app.knowledge as modern

    assert set(legacy.__all__) == set(modern.__all__)
    for name in modern.__all__:
        assert hasattr(legacy, name), f"legacy shim missing {name}"


def test_bridge_hub_knowledge_legacy_symbols_work():
    import bridge_hub_knowledge as legacy

    assert callable(legacy.calculate_cit)
    assert callable(legacy.classify_transaction)
    assert isinstance(legacy.CHART_OF_ACCOUNTS, dict)
