"""
app/compliance/rbac.py
Bridge Hub — RBAC (delegates to app/api/authz.py as source of truth)
"""
from enum import Enum
from fastapi import Request, HTTPException
from app.api.authz import ROLE_PERMISSIONS, has_role_permission, require_auth


class Role(str, Enum):
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
    AI_SUPERVISOR = "ai_supervisor"
    CLIENT = "client"


def get_role(request: Request) -> Role:
    role_str = getattr(request.state, "role", None)
    if not role_str:
        return Role.VIEWER
    try:
        return Role(role_str)
    except ValueError:
        return Role.VIEWER


def has_permission(role: Role, permission: str) -> bool:
    return has_role_permission(role.value, permission)


def require_permission(permission: str):
    """Dependency injection pattern: Depends(require_permission("approval.approve"))"""
    def checker(request: Request):
        require_auth(request)
        role = get_role(request)
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "FORBIDDEN",
                    "message": f"არ გაქვს წვდომა: {permission}",
                    "role": role.value,
                    "required": permission,
                },
            )
        return role
    return checker


def check_permission(request: Request, permission: str) -> bool:
    role = get_role(request)
    return has_permission(role, permission)


def get_role_permissions(role: Role) -> list:
    return sorted(ROLE_PERMISSIONS.get(role.value, set()))


def get_all_roles() -> dict:
    return {role.value: get_role_permissions(role) for role in Role}
