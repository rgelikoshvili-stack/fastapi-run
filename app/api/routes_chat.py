from fastapi import APIRouter
from pydantic import BaseModel
from app.api.db import get_db
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatMessageRequest(BaseModel):
    message: str
    session_id: str | None = "default"

@router.post("/message")
def send_message(payload: ChatMessageRequest):
    try:
        session_id = payload.session_id or "default"
        msg = payload.message.strip()

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO chat_messages(session_id, role, content) VALUES (%s,%s,%s)",
            (session_id,"user",msg)
        )
        conn.commit()
        cur.close()
        conn.close()

        reply = "Bridge Hub AI: მიღებულია"

        return ok_response(
            "Chat message processed",
            {"session_id": session_id, "reply": reply}
        )
    except Exception as e:
        return error_response("Chat failed", "CHAT_ERROR", str(e))

@router.get("/history")
def chat_history(session_id: str = "default"):
    from app.api.response_utils import ok_response
    return ok_response("Chat history", {
        "session_id": session_id,
        "messages": [],
        "note": "In-memory only — history resets on redeploy"
    })
