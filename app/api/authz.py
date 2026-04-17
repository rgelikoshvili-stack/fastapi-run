from fastapi import Request, HTTPException

ROLE_PERMISSIONS = {
    "admin": {
        "reports:read",
        "posting:read",
        "posting:write",
        "approval:read",
        "approval:write",
        "payroll:read",
        "payroll:write",
        "ocr:read",
        "ocr:write",
        "notifications:read",
        "notifications:write",
        "search:read",
    },
    "accountant": {
        "reports:read",
        "posting:read",
        "posting:write",
        "payroll:read",
        "payroll:write",
        "ocr:read",
        "ocr:write",
        "notifications:read",
        "search:read",
    },
    "reviewer": {
        "reports:read",
        "posting:read",
        "approval:read",
        "approval:write",
        "ocr:read",
        "notifications:read",
        "search:read",
    },
    "viewer": {
        "reports:read",
        "posting:read",
        "payroll:read",
        "ocr:read",
        "notifications:read",
        "search:read",
    },
}


def require_auth(request: Request):
    if not getattr(request.state, "authenticated", False):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHORIZED",
                "message": "ავთენტიკაცია აუცილებელია",
            },
        )


def require_permission(request: Request, permission: str):
    require_auth(request)

    role = getattr(request.state, "role", None)
    if not role:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": "როლი ვერ განისაზღვრა",
            },
        )

    allowed = ROLE_PERMISSIONS.get(role, set())
    if permission not in allowed:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": f"წვდომა აკრძალულია: საჭიროა {permission}",
            },
        )