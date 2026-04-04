import psycopg2.extras

from app.api.db import get_db
from app.api.response_utils import ok_response, error_response


def list_tenants_service():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT id, tenant_id, name, slug, plan, is_active, status, created_at, updated_at
            FROM tenants
            ORDER BY id ASC
            """
        )
        rows = [dict(r) for r in cur.fetchall()]
        return ok_response("Tenants list", {"count": len(rows), "tenants": rows})

    except Exception as e:
        return error_response("Tenants list failed", "TENANTS_LIST_ERROR", str(e))
    finally:
        cur.close()
        conn.close()


def create_tenant_service(tenant_id: str, name: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    tenant_id = (tenant_id or "").strip().lower()
    name = (name or "").strip()

    if not tenant_id:
        return error_response("Invalid tenant_id", "INVALID_TENANT_ID", "tenant_id is required")

    if not name:
        return error_response("Invalid name", "INVALID_TENANT_NAME", "name is required")

    slug = tenant_id

    try:
        cur.execute(
            """
            SELECT id
            FROM tenants
            WHERE tenant_id = %s OR slug = %s
            """,
            (tenant_id, slug),
        )
        existing = cur.fetchone()

        if existing:
            return error_response(
                "Tenant already exists",
                "TENANT_EXISTS",
                f"Tenant '{tenant_id}' already exists",
            )

        cur.execute(
            """
            INSERT INTO tenants (
                tenant_id,
                name,
                slug,
                plan,
                is_active,
                status,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, 'FREE', TRUE, 'active', NOW(), NOW())
            RETURNING id, tenant_id, name, slug, plan, is_active, status, created_at, updated_at
            """,
            (tenant_id, name, slug),
        )
        row = dict(cur.fetchone())
        conn.commit()

        return ok_response("Tenant created", row)

    except Exception as e:
        conn.rollback()
        return error_response("Tenant create failed", "TENANT_CREATE_ERROR", str(e))
    finally:
        cur.close()
        conn.close()