def test_chat_intent_engine():
    from app.api.services.intent_engine import detect_intent

    result = detect_intent("parse invoice pdf")

    assert "intent" in result


def test_chat_route_action():
    from app.api.services.action_router import route_action

    result = route_action({"message": "გადახდა"})

    assert "action" in result