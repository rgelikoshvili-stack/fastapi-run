"""
app/api/authz.py
Bridge Hub — Single RBAC Source of Truth

Middleware + routes use colon-format (e.g. "reports:read").
compliance/rbac.py delegates to this file.
"""
from fastapi import Request, HTTPException

# ── Colon-format permissions (used by middleware + routes) ──────────────────
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "reports:read",
        "posting:read",
        "posting:write",
        "approval:read",
        "approval:write",
        "approval:cfo",
        "settings:write",
        "payroll:read",
        "payroll:write",
        "ocr:read",
        "ocr:write",
        "notifications:read",
        "notifications:write",
        "search:read",
        "tenants:manage",
        "patterns:manage",
        "audit:view",
        "audit:read",
        "bank:upload",
        "bank:process",
        "export:any",
        "chat:use",
        "dashboard:admin",
        "dashboard:view",
        "inventory:read",
        "inventory:write",
        "assets:read",
        "assets:write",
        "budget:read",
        "budget:write",
        "crm:read",
        "crm:write",
        "documents:read",
        "documents:write",
    },
    "accountant": {
        "reports:read",
        "posting:read",
        "posting:write",
        "approval:read",
        "approval:write",
        "settings:write",
        "payroll:read",
        "payroll:write",
        "ocr:read",
        "ocr:write",
        "notifications:read",
        "search:read",
        "patterns:view",
        "audit:view",
        "audit:read",
        "bank:upload",
        "bank:process",
        "export:any",
        "chat:use",
        "dashboard:view",
        "inventory:read",
        "inventory:write",
        "assets:read",
        "assets:write",
        "budget:read",
        "budget:write",
        "crm:read",
        "crm:write",
        "documents:read",
        "documents:write",
    },
    "reviewer": {
        "reports:read",
        "posting:read",
        "approval:read",
        "approval:write",
        "ocr:read",
        "notifications:read",
        "search:read",
        "patterns:view",
        "audit:view",
        "audit:read",
        "export:any",
        "chat:use",
        "dashboard:view",
        "inventory:read",
        "assets:read",
        "budget:read",
        "crm:read",
        "documents:read",
    },
    "viewer": {
        "reports:read",
        "posting:read",
        "payroll:read",
        "ocr:read",
        "notifications:read",
        "search:read",
        "patterns:view",
        "audit:view",
        "audit:read",
        "export:any",
        "dashboard:view",
        "inventory:read",
        "assets:read",
        "budget:read",
        "crm:read",
        "documents:read",
    },
    "cfo": {
        "reports:read",
        "posting:read",
        "posting:write",
        "approval:read",
        "approval:write",
        "approval:cfo",
        "settings:write",
        "payroll:read",
        "audit:view",
        "audit:read",
        "export:any",
        "dashboard:view",
        "dashboard:admin",
        "budget:read",
        "budget:write",
        "crm:read",
        "documents:read",
        "documents:write",
    },
    "ai_supervisor": {
        "reports:read",
        "patterns:view",
        "patterns:manage",
        "audit:view",
        "audit:read",
        "dashboard:view",
        "chat:use",
    },
}

# ── Dot-format aliases → colon-format (for compliance/rbac.py compat) ───────
_DOT_TO_COLON: dict[str, str] = {
    "approval.approve":   "approval:write",
    "approval.reject":    "approval:write",
    "approval.correct":   "approval:write",
    "approval.view":      "approval:read",
    "posting.execute":    "posting:write",
    "learning.view":      "reports:read",
    "learning.feedback":  "approval:write",
    "export.excel":       "export:any",
    "export.pdf":         "export:any",
    "export.csv":         "export:any",
    "export.xml":         "export:any",
    "tenant.manage":      "tenants:manage",
    "patterns.view":      "patterns:view",
    "patterns.manage":    "patterns:manage",
    "audit.view":         "audit:view",
    "audit.read":         "audit:read",
    "bank.upload":        "bank:upload",
    "bank.process":       "bank:process",
    "chat.use":           "chat:use",
    "dashboard.view":     "dashboard:view",
    "dashboard.admin":    "dashboard:admin",
}


def _resolve_permission(permission: str) -> str:
    """Normalizes dot-format to colon-format if needed."""
    return _DOT_TO_COLON.get(permission, permission)


def has_role_permission(role: str, permission: str) -> bool:
    perm = _resolve_permission(permission)
    return perm in ROLE_PERMISSIONS.get(role, set())


def require_auth(request: Request):
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(
            status_code=401,
            detail={"error": "UNAUTHORIZED", "message": "ავთენტიკაცია აუცილებელია"},
        )


def require_permission(request: Request, permission: str):
    require_auth(request)
    role = getattr(request.state, "role", None)
    if not role:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "როლი ვერ განისაზღვრა"},
        )
    if not has_role_permission(role, permission):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": f"წვდომა აკრძალულია: საჭიროა {permission}",
                "role": role,
                "required": permission,
            },
        )
