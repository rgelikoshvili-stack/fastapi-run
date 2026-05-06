from fastapi import APIRouter, HTTPException
from app.api.db import get_conn, _q
from app.api.services.cache_service import cache_get, cache_set, cache_delete, CACHE_TTL
from app.api.response_utils import ok_response, error_response

router = APIRouter(prefix="/coa", tags=["coa"])


@router.get("/list")
async def coa_list(category: str = None):
    cache_key = f"coa:list:{category or 'all'}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    async with get_conn() as conn:
        if category:
            rows = await conn.fetch(_q("SELECT * FROM coa WHERE category=%s AND is_active=TRUE ORDER BY code"), category)
        else:
            rows = await conn.fetch("SELECT * FROM coa WHERE is_active=TRUE ORDER BY code")
    result = {"ok": True, "count": len(rows), "accounts": [dict(r) for r in rows]}
    cache_set(cache_key, result, CACHE_TTL["coa_list"])
    return result


@router.get("/get/{code}")
async def coa_get(code: str):
    cache_key = f"coa:code:{code}"
    cached = cache_get(cache_key)
    if cached:
        return cached
    async with get_conn() as conn:
        row = await conn.fetchrow(_q("SELECT * FROM coa WHERE code=%s"), code)
    if not row:
        raise HTTPException(404, f"Account {code} not found")
    result = {"ok": True, "account": dict(row)}
    cache_set(cache_key, result, CACHE_TTL["coa_list"])
    return result


@router.get("/search")
async def coa_search(q: str):
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("SELECT * FROM coa WHERE (name_ka ILIKE %s OR name_en ILIKE %s OR code ILIKE %s) AND is_active=TRUE ORDER BY code"),
            f"%{q}%", f"%{q}%", f"%{q}%"
        )
    return ok_response("ok", {"count": len(rows), "accounts": [dict(r) for r in rows]})


@router.get("/categories")
async def coa_categories():
    cache_key = "coa:categories"
    cached = cache_get(cache_key)
    if cached:
        return cached
    async with get_conn() as conn:
        rows = await conn.fetch("SELECT DISTINCT category, COUNT(*) as count FROM coa WHERE is_active=TRUE GROUP BY category ORDER BY category")
    result = {"ok": True, "categories": [dict(r) for r in rows]}
    cache_set(cache_key, result, CACHE_TTL["coa_list"])
    return result


@router.get("/summary")
async def coa_summary():
    cache_key = "coa:summary"
    cached = cache_get(cache_key)
    if cached:
        return cached
    async with get_conn() as conn:
        total_row = await conn.fetchrow("SELECT COUNT(*) as total FROM coa WHERE is_active=TRUE")
        total = (total_row or {}).get("total", 0)
        breakdown_rows = await conn.fetch("""
            SELECT
                CASE
                    WHEN code LIKE '1%' THEN 'assets'
                    WHEN code LIKE '2%' THEN 'assets'
                    WHEN code LIKE '3%' THEN 'liabilities'
                    WHEN code LIKE '4%' THEN 'equity'
                    WHEN code LIKE '6%' THEN 'revenue'
                    WHEN code LIKE '7%' THEN 'expenses'
                    WHEN code LIKE '8%' THEN 'other'
                    ELSE 'other'
                END AS type,
                COUNT(*) AS count
            FROM coa
            WHERE is_active=TRUE
            GROUP BY 1
            ORDER BY 1
        """)
    breakdown = {r["type"]: int(r["count"]) for r in breakdown_rows}
    result = {"ok": True, "total": total, "breakdown": breakdown}
    cache_set(cache_key, result, CACHE_TTL["coa_list"])
    return result
