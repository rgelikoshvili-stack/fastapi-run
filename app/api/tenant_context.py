DEFAULT_TENANT_ID = "default"


def resolve_tenant_id(value: str | None) -> str:
    tenant_id = (value or "").strip()
    return tenant_id or DEFAULT_TENANT_ID