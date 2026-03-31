from fastapi import APIRouter
from pydantic import BaseModel

from app.api.response_utils import ok_response, error_response
from app.services.route_bridge_service import bridge_chat_payload

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    message: str
    session_id: str | None = "default"


@router.post("/message")
def send_message(payload: ChatMessageRequest):
    try:
        return bridge_chat_payload(payload.model_dump())
    except Exception as e:
        return error_response("Chat route failed", "CHAT_ROUTE_ERROR", str(e))


@router.get("/history")
def chat_history(session_id: str = "default"):
    return ok_response(
        "Chat history",
        {
            "session_id": session_id,
            "messages": [],
            "note": "In-memory only — history resets on redeploy",
        },
    )