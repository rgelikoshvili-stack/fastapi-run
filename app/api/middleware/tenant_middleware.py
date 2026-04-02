from fastapi import Request


async def tenant_middleware(request: Request, call_next):
    tenant_id = request.headers.get("X-Tenant-ID", "default")

    request.state.tenant_id = tenant_id

    response = await call_next(request)
    return response