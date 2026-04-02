def test_memory_priority():
    from app.api.services.memory_priority_engine import merge_memory_sources

    result = merge_memory_sources(
        {"context_used": True},
        {"source": "rules", "confidence": 0.5},
    )

    assert result["source"] == "transaction_memory"