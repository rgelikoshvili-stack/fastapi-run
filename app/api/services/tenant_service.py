from app.api.db import get_conn, _q
from app.api.response_utils import ok_response, error_response


async def list_tenants_service():
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch("""
                SELECT id, tenant_id, name, slug, plan, is_active, status, created_at, updated_at
                FROM tenants
                ORDER BY id ASC
            """)]
        return ok_response("Tenants list", {"count": len(rows), "tenants": rows})
    except Exception as e:
        return error_response("Tenants list failed", "TENANTS_LIST_ERROR", str(e))


async def create_tenant_service(tenant_id: str, name: str):
    tenant_id = (tenant_id or "").strip().lower()
    name = (name or "").strip()

    if not tenant_id:
        return error_response("Invalid tenant_id", "INVALID_TENANT_ID", "tenant_id is required")
    if not name:
        return error_response("Invalid name", "INVALID_TENANT_NAME", "name is required")

    slug = tenant_id

    try:
        async with get_conn() as conn:
            existing = await conn.fetchrow(_q(
                "SELECT id FROM tenants WHERE tenant_id = %s OR slug = %s"
            ), tenant_id, slug)
            if existing:
                return error_response(
                    "Tenant already exists", "TENANT_EXISTS",
                    f"Tenant '{tenant_id}' already exists",
                )
            row = dict(await conn.fetchrow(_q("""
                INSERT INTO tenants (
                    tenant_id, name, slug, plan, is_active, status, created_at, updated_at
                )
                VALUES (%s, %s, %s, 'FREE', TRUE, 'active', NOW(), NOW())
                RETURNING id, tenant_id, name, slug, plan, is_active, status, created_at, updated_at
            """), tenant_id, name, slug))
        return ok_response("Tenant created", row)
    except Exception as e:
        return error_response("Tenant create failed", "TENANT_CREATE_ERROR", str(e))
