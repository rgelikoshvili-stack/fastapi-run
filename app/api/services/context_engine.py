from app.api.services.transaction_memory_service import find_memory_match


def build_context(payload: dict) -> dict:
    description = payload.get("description", "") or ""
    partner = payload.get("partner", "") or ""

    memory_match = find_memory_match(description, partner)

    return {
        "ok": True,
        "memory_match": memory_match,
        "context_used": bool(memory_match),
        "context_source": "transaction_memory" if memory_match else None,
    }