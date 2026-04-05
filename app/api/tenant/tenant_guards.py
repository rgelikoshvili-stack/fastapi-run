from fastapi import Request, HTTPException
from app.api.tenant_context import resolve_tenant_id


def require_tenant(request: Request) -> str:
    """
    tenant_id ამოიღებს request-იდან.
    თუ არ არის — 400 error.
    """
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if not tenant_id or tenant_id == "":
        raise HTTPException(
            status_code=400,
            detail={"error": "TENANT_REQUIRED", "message": "tenant_id სავალდებულოა"}
        )
    return tenant_id


def require_admin_tenant(request: Request) -> str:
    """
    მხოლოდ admin tenant-ებისთვის.
    """
    tenant_id = require_tenant(request)
    admin_tenants = ["default", "admin"]
    if tenant_id not in admin_tenants:
        raise HTTPException(
            status_code=403,
            detail={"error": "FORBIDDEN", "message": "მხოლოდ admin-ისთვის"}
        )
    return tenant_id


def guard_cross_tenant(request: Request, resource_tenant_id: str) -> bool:
    """
    ამოწმებს: შეუძლია თუ არა ამ tenant-ს ამ resource-ზე წვდომა.
    cross-tenant წვდომა დაბლოკილია.
    """
    current_tenant = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    if current_tenant != resource_tenant_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "CROSS_TENANT_FORBIDDEN",
                "message": f"სხვის tenant-ზე წვდომა აკრძალულია"
            }
        )
    return True


def get_tenant_or_default(request: Request) -> str:
    """
    tenant_id ამოიღებს ან default-ს დააბრუნებს.
    exception არ ისვრის.
    """
    return resolve_tenant_id(getattr(request.state, "tenant_id", None))