"""Chat178: strict tenant-scoped Vector retrieval and posted-ledger SQL joins.

Pure synthetic tests; no filesystem indexing, remote embeddings, Cloud SQL,
Production credentials or Chroma mutation.
"""
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def vector_module(monkeypatch):
    """Execute vector search code against stubbed optional Chroma imports.

    Chat178 does not add ChromaDB to the production dependency set. The API
    remains disabled; only the strict filtering logic is tested in CI.
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    package = types.ModuleType("chromadb")
    package.__path__ = []
    config = types.ModuleType("chromadb.config")
    config.Settings = object
    monkeypatch.setitem(sys.modules, "chromadb", package)
    monkeypatch.setitem(sys.modules, "chromadb.config", config)
    filename = Path(__file__).resolve().parents[2] / "bridge_hub_vector_db.py"
    spec = importlib.util.spec_from_file_location("chat178_vector_test_target", filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeLearned:
    def __init__(self):
        self.called = []
        self.total = 4
        self.response = {
            "documents": [[
                "Synthetic tenant A correction",
                "Synthetic tenant B secret",
                "Synthetic unlabeled legacy rule",
                "Synthetic tenant A second correction",
            ]],
            "metadatas": [[
                {"tenant_id": "t_alpha", "source": "synthetic"},
                {"tenant_id": "t_beta", "source": "synthetic"},
                {},
                {"tenant_id": "t_alpha", "source": "synthetic", "filepath": "/private"},
            ]],
            "distances": [[0.01, 0.0, 0.0, 0.2]],
        }

    def count(self):
        return self.total

    def query(self, **kwargs):
        self.called.append(kwargs)
        return self.response


def test_scoped_vector_only_queries_learned_collection_and_filters_twice(monkeypatch, vector_module):
    vector = vector_module

    learned = FakeLearned()
    base = MagicMock()
    base.count.side_effect = AssertionError("Unclassified base files must NOT be queried")
    monkeypatch.setattr(vector, "_get_client", lambda: (None, base, learned))
    monkeypatch.setattr(vector, "_get_embedder", lambda: lambda sentences: [[0.1, 0.2, 0.3]])
    found = vector.tenant_learned_search(" expense ", "t_alpha", top_k=4)
    assert [r["text"] for r in found] == [
        "Synthetic tenant A correction", "Synthetic tenant A second correction"
    ]
    assert all(r["source"] == "tenant_human_correction" for r in found)
    assert all("filepath" not in r for r in found)
    assert len(learned.called) == 1
    kwargs = learned.called[0]
    assert kwargs["where"] == {"tenant_id": "t_alpha"}
    assert kwargs["query_embeddings"] == [[0.1, 0.2, 0.3]]
    assert kwargs["n_results"] == 4
    base.count.assert_not_called()


@pytest.mark.parametrize("tenant", [
    None, "", " ", "global", "GLOBAL", "default", "public",
    "tenant:other", "tenant/other", "a" * 129, "foo\nbar",
])
def test_missing_global_or_invalid_tenant_is_rejected_before_vector_io(monkeypatch, tenant, vector_module):
    vector = vector_module

    monkeypatch.setattr(
        vector, "_get_client",
        lambda: (_ for _ in ()).throw(AssertionError("Invalid tenant triggered IO"))
    )
    with pytest.raises(ValueError):
        vector.tenant_learned_search("invoice", tenant)


@pytest.mark.parametrize("kwargs", [
    {"query": ""}, {"query": " "}, {"query": "x" * 2001},
    {"top_k": 0}, {"top_k": 21}, {"top_k": True},
    {"min_score": -1}, {"min_score": 1.1}, {"min_score": float("nan")},
])
def test_invalid_vector_request_fails_before_io(monkeypatch, kwargs, vector_module):
    vector = vector_module

    monkeypatch.setattr(
        vector, "_get_client",
        lambda: (_ for _ in ()).throw(AssertionError("Invalid request triggered IO"))
    )
    data = {"query": "income", "tenant_id": "t_alpha"}
    data.update(kwargs)
    with pytest.raises(ValueError):
        vector.tenant_learned_search(**data)


def test_vector_empty_collection_does_not_load_remote_embedding(monkeypatch, vector_module):
    vector = vector_module

    learned = FakeLearned()
    learned.total = 0
    monkeypatch.setattr(vector, "_get_client", lambda: (None, None, learned))
    monkeypatch.setattr(
        vector, "_get_embedder",
        lambda: (_ for _ in ()).throw(AssertionError("Unneeded embedding load"))
    )
    assert vector.tenant_learned_search("income", "t_alpha") == []
    assert not learned.called


@pytest.mark.parametrize("bad", [
    {"documents": [[]], "metadatas": [[{}]], "distances": [[]]},
    {"documents": [[]], "metadatas": [], "distances": [[]]},
    {"documents": [], "metadatas": [[]], "distances": [[]]},
])
def test_vector_malformed_result_is_never_returned(monkeypatch, bad, vector_module):
    vector = vector_module

    learned = FakeLearned()
    learned.response = bad
    monkeypatch.setattr(vector, "_get_client", lambda: (None, None, learned))
    monkeypatch.setattr(vector, "_get_embedder", lambda: lambda q: [[0.1, 0.2]])
    with pytest.raises(RuntimeError, match="Vector search results unavailable"):
        vector.tenant_learned_search("income", "t_alpha")


def test_vector_backend_query_errors_do_not_fallback_to_global_data(monkeypatch, vector_module):
    vector = vector_module

    learned = FakeLearned()
    learned.query = MagicMock(side_effect=RuntimeError("synthetic query error"))
    monkeypatch.setattr(vector, "_get_client", lambda: (None, None, learned))
    monkeypatch.setattr(vector, "_get_embedder", lambda: lambda q: [[0.1, 0.2]])
    with pytest.raises(RuntimeError):
        vector.tenant_learned_search("income", "t_alpha")
    learned.query.assert_called_once()
    assert learned.query.call_args.kwargs["where"] == {"tenant_id": "t_alpha"}


@pytest.mark.parametrize("embedding", [[], [float("nan")], [float("inf")], ["invalid"], None])
def test_chat179_invalid_embeddings_fail_before_query(monkeypatch, vector_module, embedding):
    learned = FakeLearned()
    learned.query = MagicMock(side_effect=AssertionError("Invalid embedding reached store"))
    monkeypatch.setattr(vector_module, "_get_client", lambda: (None, None, learned))
    monkeypatch.setattr(vector_module, "_get_embedder", lambda: lambda q: [embedding])
    with pytest.raises(RuntimeError, match="Vector embeddings unavailable"):
        vector_module.tenant_learned_search("income", "t_alpha")
    learned.query.assert_not_called()


@pytest.mark.parametrize("name,params", [
    ("_build_pnl_posted_ledger_query", ("t_alpha", None, None)),
    ("_build_balance_sheet_posted_ledger_query", ("t_alpha", None)),
    ("_build_cashflow_posted_ledger_query", ("t_alpha", None, None)),
    ("_build_posted_trial_balance_as_of_query", ("t_alpha", None)),
])
def test_posted_ledger_queries_join_on_header_and_line_tenant(name, params):
    from app.api.services import financial_statements_service as finance

    sql, values = getattr(finance, name)(*params)
    assert "jel.tenant_id = jeh.tenant_id" in sql
    assert "jeh.tenant_id = $1" in sql
    assert "journal_drafts" not in sql
    assert values[0] == "t_alpha"
