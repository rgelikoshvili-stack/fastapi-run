"""
app/compliance/rbac.py
Bridge Hub — Role-Based Access Control
"""
from enum import Enum
from fastapi import Request, HTTPException


# ========== Roles ==========

class Role(str, Enum):
    ADMIN = "admin"
    ACCOUNTANT = "accountant"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
    CLIENT = "client"


# ========== Permission Matrix ==========

PERMISSIONS = {
    Role.ADMIN: {
        "approval.approve",
        "approval.reject",
        "approval.correct",
        "approval.view",
        "learning.view",
        "learning.feedback",
        "export.excel",
        "export.pdf",
        "export.csv",
        "export.xml",
        "tenant.manage",
        "patterns.view",
        "patterns.manage",
        "audit.view",
        "posting.execute",
        "bank.upload",
        "bank.process",
        "chat.use",
        "dashboard.view",
        "dashboard.admin",
    },
    Role.ACCOUNTANT: {
        "approval.approve",
        "approval.reject",
        "approval.correct",
        "approval.view",
        "learning.view",
        "learning.feedback",
        "export.excel",
        "export.pdf",
        "export.csv",
        "export.xml",
        "patterns.view",
        "audit.view",
        "posting.execute",
        "bank.upload",
        "bank.process",
        "chat.use",
        "dashboard.view",
    },
    Role.REVIEWER: {
        "approval.view",
        "approval.approve",
        "approval.reject",
        "learning.view",
        "export.excel",
        "export.pdf",
        "export.csv",
        "patterns.view",
        "audit.view",
        "dashboard.view",
        "chat.use",
    },
    Role.VIEWER: {
        "approval.view",
        "learning.view",
        "export.csv",
        "patterns.view",
        "audit.view",
        "dashboard.view",
    },
    Role.CLIENT: {
        "approval.view",
        "bank.upload",
        "dashboard.view",
        "export.csv",
    },
}


# ========== Role Resolution ==========

def get_role(request: Request) -> Role:
    """
    Request-იდან role-ის ამოღება.
    middleware-ი ადგენს request.state.role-ს.
    """
    role_str = getattr(request.state, "role", None)
    if not role_str:
        return Role.VIEWER
    try:
        return Role(role_str)
    except ValueError:
        return Role.VIEWER


def has_permission(role: Role, permission: str) -> bool:
    """
    შეამოწმებს: აქვს თუ არა ამ role-ს ეს permission.
    """
    return permission in PERMISSIONS.get(role, set())


# ========== Permission Guards ==========

def require_permission(permission: str):
    """
    Dependency injection-ისთვის:
    @app.get("/route")
    def route(p=Depends(require_permission("approval.approve"))):
    """
    def checker(request: Request):
        role = get_role(request)
        if not has_permission(role, permission):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "FORBIDDEN",
                    "message": f"არ გაქვს წვდომა: {permission}",
                    "role": role,
                    "required": permission,
                }
            )
        return role
    return checker


def check_permission(request: Request, permission: str) -> bool:
    """
    მარტივი შემოწმება — exception-ის გარეშე.
    """
    role = get_role(request)
    return has_permission(role, permission)


# ========== Role Info ==========

def get_role_permissions(role: Role) -> list:
    """
    role-ის ყველა permission-ის სია.
    """
    return sorted(list(PERMISSIONS.get(role, set())))


def get_all_roles() -> dict:
    """
    ყველა role და მათი permissions.
    """
    return {
        role.value: get_role_permissions(role)
        for role in Role
    }