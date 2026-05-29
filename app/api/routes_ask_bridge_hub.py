"""app/api/routes_ask_bridge_hub.py — Ask Bridge Hub (Task 15)."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator

from app.api.authz import require_permission
from app.api.response_utils import error_response, ok_response
from app.api.services.ask_bridge_hub_service import ask, parse_intent
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/ask", tags=["ask-bridge-hub"])


class AskPayload(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be blank")
        return v


@router.post("")
async def ask_question(payload: AskPayload, request: Request):
    require_permission(request, "chat:use")
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    result = await ask(tenant_id, payload.question)
    return ok_response(result["answer"], result)


@router.post("/parse")
async def parse_question(payload: AskPayload, request: Request):
    """Return the parsed intent without running the DB query — useful for debugging."""
    require_permission(request, "chat:use")
    intent = parse_intent(payload.question)
    return ok_response("Intent parsed", intent)
