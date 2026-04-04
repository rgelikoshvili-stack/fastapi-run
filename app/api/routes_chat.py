from fastapi import APIRouter, Request
from pydantic import BaseModel
from app.api.response_utils import ok_response, error_response
from app.api.tenant_context import resolve_tenant_id
import os, anthropic

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatMessageRequest(BaseModel):
    message: str
    session_id: str | None = "default"

@router.post("/message")
def send_message(payload: ChatMessageRequest, request: Request):
    try:
        tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system="""შენ ხარ Bridge Hub-ის AI ასისტენტი — ქართული AI საბუღალტრო სისტემა.
ხელმისაწვდომი სისტემები: Balance.ge, 1C:Enterprise, ORIS, RS.GE.
გვიპასუხე ქართულად, მოკლედ და კონკრეტულად.""",
            messages=[{"role": "user", "content": payload.message}]
        )
        reply = resp.content[0].text
        return ok_response("Chat response", {"reply": reply, "tenant_id": tenant_id})
    except Exception as e:
        return error_response("Chat failed", "CHAT_ERROR", str(e))

@router.get("/history")
def chat_history(session_id: str = "default"):
    return ok_response("Chat history", {"session_id": session_id, "messages": []})
