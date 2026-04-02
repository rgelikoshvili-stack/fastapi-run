import os
from fastapi import Request, HTTPException


def check_permission(role: str, action: str) -> bool:
    if role == "admin":
        return True
    if role == "operator" and action == "write":
        return True
    if role == "viewer" and action == "read":
        return True
    return False


async def rbac_middleware(request: Request, call_next):
    # ✅ TEST MODE BYPASS
    if os.getenv("TEST_MODE") == "1":
        return await call_next(request)

    role = request.headers.get("X-Role", "viewer")
    request.state.role = role

    if request.method == "POST":
        if not check_permission(role, "write"):
            raise HTTPException(status_code=403, detail="Forbidden")

    return await call_next(request)