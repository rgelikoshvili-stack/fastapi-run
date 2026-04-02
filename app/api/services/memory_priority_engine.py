def merge_memory_sources(context: dict, classification: dict) -> dict:
    result = {
        "source": "rules",
        "confidence": classification.get("confidence", 0),
    }

    # PRIORITY 1 — ERP MEMORY
    if classification.get("source") == "erp_history":
        return {
            "source": "erp_history",
            "confidence": 0.95,
        }

    # PRIORITY 2 — TRANSACTION MEMORY
    if context.get("context_used"):
        return {
            "source": "transaction_memory",
            "confidence": 0.90,
        }

    # PRIORITY 3 — PATTERNS
    if classification.get("source", "").startswith("pattern"):
        return {
            "source": "pattern",
            "confidence": classification.get("confidence", 0.8),
        }

    return result