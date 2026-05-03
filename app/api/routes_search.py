from fastapi import APIRouter, Query, Request
from app.api.db import get_conn, _q
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/search", tags=["search"])


async def _ensure_tables(conn):
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS search_index (
            id SERIAL PRIMARY KEY,
            doc_id VARCHAR(100),
            doc_type VARCHAR(50),
            filename VARCHAR(300),
            amount FLOAT,
            state VARCHAR(50),
            tags TEXT[],
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            query TEXT,
            results_count INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


async def _run_search(tenant_id: str, q: str = "", state: str = "",
                      min_amount: float = 0, max_amount: float = 999999999):
    async with get_conn() as conn:
        conditions = ["tenant_id = $1"]
        params: list = [tenant_id]

        if q:
            conditions.append(f"(p.filename ILIKE ${len(params)+1})")
            params.append(f"%{q}%")
        if state:
            conditions.append(f"p.state = ${len(params)+1}")
            params.append(state)

        where = " AND ".join(conditions)

        try:
            docs = [dict(r) for r in await conn.fetch(f"""
                SELECT p.run_id, p.filename, p.state, p.created_at
                FROM pipeline_runs p
                WHERE {where}
                ORDER BY p.created_at DESC
                LIMIT 50
            """, *params)]
        except Exception:
            docs = []

        tx_results = []
        if q:
            try:
                tx_results = [dict(r) for r in await conn.fetch(_q("""
                    SELECT id, bank, date, amount, description
                    FROM bank_transactions
                    WHERE tenant_id = %s
                      AND description ILIKE %s
                      AND amount >= %s
                      AND amount <= %s
                    ORDER BY created_at DESC
                    LIMIT 20
                """), tenant_id, f"%{q}%", min_amount, max_amount)]
            except Exception:
                tx_results = []

        coa_results = []
        if q:
            try:
                coa_results = [dict(r) for r in await conn.fetch(_q("""
                    SELECT code, name_ka, name_en, category
                    FROM coa
                    WHERE name_ka ILIKE %s OR name_en ILIKE %s OR code::text ILIKE %s
                    LIMIT 30
                """), f"%{q}%", f"%{q}%", f"%{q}%")]
            except Exception:
                coa_results = []

        total_results = len(docs) + len(tx_results) + len(coa_results)

        try:
            await conn.execute(_q("""
                INSERT INTO search_history (query, results_count, tenant_id) VALUES (%s, %s, %s)
            """), q, total_results, tenant_id)
        except Exception:
            try:
                await conn.execute(_q("""
                    INSERT INTO search_history (query, results_count) VALUES (%s, %s)
                """), q, total_results)
            except Exception:
                pass

    return {
        "ok": True, "query": q, "state": state,
        "min_amount": min_amount, "max_amount": max_amount,
        "total_results": total_results,
        "documents": docs, "transactions": tx_results, "coa_accounts": coa_results,
    }


@router.get("")
@limiter.limit("30/minute")
async def search_alias(
    request: Request,
    q: str = Query(""),
    state: str = Query(""),
    min_amount: float = Query(0, ge=0),
    max_amount: float = Query(999999999, ge=0),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await _run_search(tenant_id=tenant_id, q=q, state=state,
                             min_amount=min_amount, max_amount=max_amount)


@router.post("/query")
@limiter.limit("30/minute")
async def search_query(request: Request, q: str = "", state: str = "",
                       min_amount: float = 0, max_amount: float = 999999999):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return await _run_search(tenant_id=tenant_id, q=q, state=state,
                             min_amount=min_amount, max_amount=max_amount)


@router.get("/filters")
@limiter.limit("30/minute")
async def get_filters(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        try:
            states = [r["state"] for r in await conn.fetch(
                _q("SELECT DISTINCT state FROM pipeline_runs WHERE state IS NOT NULL AND tenant_id = %s"), tenant_id)]
        except Exception:
            states = []
        try:
            banks = [r["bank"] for r in await conn.fetch(
                _q("SELECT DISTINCT bank FROM bank_transactions WHERE bank IS NOT NULL AND tenant_id = %s"), tenant_id)]
        except Exception:
            banks = []
        try:
            categories = [r["category"] for r in await conn.fetch(
                "SELECT DISTINCT category FROM coa WHERE category IS NOT NULL")]
        except Exception:
            categories = []
    return {"ok": True, "states": states, "banks": banks, "coa_categories": categories}


@router.get("/recent")
@limiter.limit("30/minute")
async def recent_searches(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        try:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT query, results_count, created_at
                FROM search_history
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT 20
            """), tenant_id)]
        except Exception:
            rows = []
    return {"ok": True, "recent_searches": rows}


@router.get("/stats")
@limiter.limit("30/minute")
async def search_stats(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    async with get_conn() as conn:
        try:
            total_docs = await conn.fetchval(_q("SELECT COUNT(*) FROM pipeline_runs WHERE tenant_id = %s"), tenant_id) or 0
        except Exception:
            total_docs = 0
        try:
            total_txs = await conn.fetchval(_q("SELECT COUNT(*) FROM bank_transactions WHERE tenant_id = %s"), tenant_id) or 0
        except Exception:
            total_txs = 0
        try:
            total_coa = await conn.fetchval("SELECT COUNT(*) FROM coa") or 0
        except Exception:
            total_coa = 0
        try:
            total_searches = await conn.fetchval(_q("SELECT COUNT(*) FROM search_history WHERE tenant_id = %s"), tenant_id) or 0
        except Exception:
            total_searches = 0
    return {
        "ok": True,
        "indexed": {"documents": total_docs, "transactions": total_txs,
                    "coa_accounts": total_coa, "total": total_docs + total_txs + total_coa},
        "total_searches": total_searches,
    }
