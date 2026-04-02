def check_permission(role: str, action: str) -> bool:
    permissions = {
        "admin": ["*"],
        "accountant": ["read", "write", "approve"],
        "reviewer": ["read", "approve"],
        "viewer": ["read"],
    }

    allowed = permissions.get(role, [])

    return "*" in allowed or action in allowed