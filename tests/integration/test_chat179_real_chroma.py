"""Real disposable Chroma; optional ONNX test is REQUIRED in dedicated CI.

Only synthetic text in pytest's temporary directory. No historical vectors,
file indexing, public API activation, cloud DB or customer data.
"""
import importlib.util
import os
from pathlib import Path

import pytest

chromadb = pytest.importorskip("chromadb")


@pytest.fixture
def real_vector(tmp_path, monkeypatch):
    from chromadb.config import Settings

    path = Path(__file__).resolve().parents[2] / "bridge_hub_vector_db.py"
    spec = importlib.util.spec_from_file_location("chat179_real_vector", path)
    vector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vector)
    client = chromadb.PersistentClient(
        path=str(tmp_path / "chroma"), settings=Settings(anonymized_telemetry=False),
    )
    base = client.create_collection(
        vector.COLLECTION_NAME, metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )
    learned = client.create_collection(
        vector.LEARN_COLLECTION, metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )
    monkeypatch.setattr(vector, "_chroma_client", client)
    monkeypatch.setattr(vector, "_collection", base)
    monkeypatch.setattr(vector, "_learn_collection", learned)
    monkeypatch.setattr(vector, "_get_embedder", lambda: lambda q: [[1., 0., 0.]])
    return vector, client, base, learned


def seed(base, learned):
    # Identical embeddings make a missing metadata filter maximally visible.
    base.add(ids=["private-base"], embeddings=[[1., 0., 0.]],
             documents=["unclassified base secret"], metadatas=[{"source": "old-file"}])
    learned.add(
        ids=["alpha", "beta", "legacy", "global"],
        embeddings=[[1., 0., 0.]] * 4,
        documents=["alpha-only correction", "beta-only correction", "legacy-secret", "global-secret"],
        metadatas=[{"tenant_id": "t_alpha", "filepath": "/synthetic/private"},
                   {"tenant_id": "t_beta"}, {"source": "legacy"}, {"tenant_id": "global"}],
    )


@pytest.mark.parametrize("tenant,expected", [
    ("t_alpha", ["alpha-only correction"]), ("t_beta", ["beta-only correction"]),
    ("t_empty", []), ("T_ALPHA", []),
])
def test_actual_metadata_filter_excludes_other_tenants_and_global(real_vector, tenant, expected):
    vector, client, base, learned = real_vector
    seed(base, learned)
    before_base, before_learned = base.get(), learned.get()
    result = vector.tenant_learned_search("expense", tenant, top_k=20)
    assert [r["text"] for r in result] == expected
    assert all(set(r) == {"text", "source", "category", "score"} for r in result)
    assert base.get() == before_base and learned.get() == before_learned


def test_actual_cosine_threshold_top_k_and_persisted_reopen(real_vector):
    vector, client, base, learned = real_vector
    learned.add(
        ids=["near", "middle", "opposite"],
        embeddings=[[1., 0., 0.], [.8, .6, 0.], [-1., 0., 0.]],
        documents=["near correction", "middle correction", "opposite correction"],
        metadatas=[{"tenant_id": "t_alpha"}] * 3,
    )
    assert [r["text"] for r in vector.tenant_learned_search(
        "expense", "t_alpha", top_k=3, min_score=.9,
    )] == ["near correction"]
    assert [r["text"] for r in vector.tenant_learned_search(
        "expense", "t_alpha", top_k=1, min_score=0,
    )] == ["near correction"]
    # Reopening a persisted collection must preserve filters and records.
    vector._learn_collection = client.get_collection(vector.LEARN_COLLECTION, embedding_function=None)
    assert len(vector.tenant_learned_search("expense", "t_alpha", top_k=3, min_score=.7)) == 2


def test_actual_empty_collection_needs_no_embedding(real_vector, monkeypatch):
    vector, client, base, learned = real_vector
    monkeypatch.setattr(vector, "_get_embedder", lambda: pytest.fail("Empty store loaded model"))
    assert vector.tenant_learned_search("expense", "t_alpha") == []


@pytest.mark.skipif(os.getenv("CHAT179_REAL_EMBEDDING_TEST") != "1",
                    reason="Dedicated vector CI opts into real local ONNX inference")
def test_actual_default_onnx_embedding_and_tenant_privacy(tmp_path, monkeypatch):
    from chromadb.config import Settings
    from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

    path = Path(__file__).resolve().parents[2] / "bridge_hub_vector_db.py"
    spec = importlib.util.spec_from_file_location("chat179_onnx_vector", path)
    vector = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vector)
    monkeypatch.setattr(ONNXMiniLM_L6_V2, "DOWNLOAD_PATH", tmp_path / "onnx-model")
    client = chromadb.PersistentClient(
        path=str(tmp_path / "onnx-chroma"), settings=Settings(anonymized_telemetry=False),
    )
    base = client.create_collection(vector.COLLECTION_NAME, embedding_function=None)
    learned = client.create_collection(
        vector.LEARN_COLLECTION, metadata={"hnsw:space": "cosine"}, embedding_function=None,
    )
    vector._chroma_client, vector._collection, vector._learn_collection = client, base, learned
    text = "საბანკო საკომისიო / bank commission synthetic correction"
    embeddings = vector._get_embedder()([text, text])
    assert len(embeddings) == 2 and len(embeddings[0]) == 384
    learned.add(ids=["onnx-alpha", "onnx-beta"], embeddings=embeddings,
                documents=[text, "beta synthetic secret"],
                metadatas=[{"tenant_id": "t_alpha"}, {"tenant_id": "t_beta"}])
    result = vector.tenant_learned_search(text, "t_alpha", top_k=2, min_score=.9)
    assert [r["text"] for r in result] == [text]
    assert base.count() == 0 and learned.count() == 2
