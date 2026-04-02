from app.api.services.intent_engine import detect_intent


def route_action(payload: dict) -> dict:
    message = (payload.get("message", "") or "").lower()

    intent = detect_intent(message)

    if intent["intent"] == "parse_invoice":
        return {
            "action": "invoice.parse",
            "mode": "preview",
        }

    if intent["intent"] == "post_transaction":
        return {
            "action": "posting.apply",
            "mode": "execute",
        }

    if intent["intent"] == "show_data":
        return {
            "action": "dashboard.show",
            "mode": "read",
        }

    if "approve" in message or "დამტკიცება" in message or "დაამტკიცე" in message:
        return {
            "action": "approval.approve",
            "mode": "execute",
        }

    if "reject" in message or "უარყავი" in message or "არ დაამტკიცო" in message:
        return {
            "action": "approval.reject",
            "mode": "execute",
        }

    return {
        "action": "unknown",
        "mode": "none",
    }