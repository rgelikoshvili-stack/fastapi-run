from fastapi import APIRouter, Query, Request
import psycopg2
import psycopg2.extras
from app.api.db import get_db
from app.api.security import limiter
from app.api.tenant_context import resolve_tenant_id

router = APIRouter(prefix="/search", tags=["search"])


def ensure_tables(cur):
    cur.execute("""
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
    cur.execute("""
        CREATE TABLE IF NOT EXISTS search_history (
            id SERIAL PRIMARY KEY,
            query TEXT,
            results_count INT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)


def _run_search(tenant_id: str, q: str = "", state: str = "", min_amount: float = 0, max_amount: float = 999999999):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        ensure_tables(cur)
        conn.commit()

        conditions = ["tenant_id = %s"]
        params = [tenant_id]

        if q:
            conditions.append("(p.filename ILIKE %s)")
            params.append(f"%{q}%")

        if state:
            conditions.append("p.state = %s")
            params.append(state)

        where = " AND ".join(conditions)

        try:
            cur.execute(f"""
                SELECT p.run_id, p.filename, p.state, p.created_at
                FROM pipeline_runs p
                WHERE {where}
                ORDER BY p.created_at DESC
                LIMIT 50
            """, params)
            docs = [dict(r) for r in cur.fetchall()]
        except Exception:
            docs = []

        tx_results = []
        if q:
            try:
                cur.execute("""
                    SELECT id, bank, date, amount, description
                    FROM bank_transactions
                    WHERE tenant_id = %s
                      AND description ILIKE %s
                      AND amount >= %s
                      AND amount <= %s
                    ORDER BY created_at DESC
                    LIMIT 20
                """, (tenant_id, f"%{q}%", min_amount, max_amount))
                tx_results = [dict(r) for r in cur.fetchall()]
            except Exception:
                tx_results = []

        coa_results = []
        if q:
            try:
                cur.execute("""
                    SELECT code, name_ka, name_en, category
                    FROM coa
                    WHERE name_ka ILIKE %s OR name_en ILIKE %s OR code::text ILIKE %s
                    LIMIT 30
                """, (f"%{q}%", f"%{q}%", f"%{q}%"))
                coa_results = [dict(r) for r in cur.fetchall()]
            except Exception:
                coa_results = []

        total_results = len(docs) + len(tx_results) + len(coa_results)

        try:
            cur.execute(
                "INSERT INTO search_history (query, results_count, tenant_id) VALUES (%s, %s, %s)",
                (q, total_results, tenant_id)
            )
            conn.commit()
        except Exception:
            try:
                cur.execute(
                    "INSERT INTO search_history (query, results_count) VALUES (%s, %s)",
                    (q, total_results)
                )
                conn.commit()
            except Exception:
                conn.rollback()

        return {
            "ok": True,
            "query": q,
            "state": state,
            "min_amount": min_amount,
            "max_amount": max_amount,
            "total_results": total_results,
            "documents": docs,
            "transactions": tx_results,
            "coa_accounts": coa_results,
        }

    finally:
        cur.close()
        conn.close()


@router.get("")
@limiter.limit("30/minute")
def search_alias(
    request: Request,
    q: str = Query("", description="Search query"),
    state: str = Query("", description="Filter by state"),
    min_amount: float = Query(0, ge=0),
    max_amount: float = Query(999999999, ge=0),
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return _run_search(tenant_id=tenant_id, q=q, state=state, min_amount=min_amount, max_amount=max_amount)


@router.post("/query")
@limiter.limit("30/minute")
def search_query(
    request: Request,
    q: str = "",
    state: str = "",
    min_amount: float = 0,
    max_amount: float = 999999999,
):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    return _run_search(tenant_id=tenant_id, q=q, state=state, min_amount=min_amount, max_amount=max_amount)


@router.get("/filters")
@limiter.limit("30/minute")
def get_filters(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        ensure_tables(cur)
        conn.commit()

        try:
            cur.execute(
                "SELECT DISTINCT state FROM pipeline_runs WHERE state IS NOT NULL AND tenant_id = %s",
                (tenant_id,),
            )
            states = [r["state"] for r in cur.fetchall()]
        except Exception:
            states = []

        try:
            cur.execute(
                "SELECT DISTINCT bank FROM bank_transactions WHERE bank IS NOT NULL AND tenant_id = %s",
                (tenant_id,),
            )
            banks = [r["bank"] for r in cur.fetchall()]
        except Exception:
            banks = []

        try:
            cur.execute("SELECT DISTINCT category FROM coa WHERE category IS NOT NULL")
            categories = [r["category"] for r in cur.fetchall()]
        except Exception:
            categories = []

        return {
            "ok": True,
            "states": states,
            "banks": banks,
            "coa_categories": categories,
        }

    finally:
        cur.close()
        conn.close()


@router.get("/recent")
@limiter.limit("30/minute")
def recent_searches(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        ensure_tables(cur)
        conn.commit()

        try:
            cur.execute("""
                SELECT query, results_count, created_at
                FROM search_history
                WHERE tenant_id = %s
                ORDER BY created_at DESC
                LIMIT 20
            """, (tenant_id,))
            rows = [dict(r) for r in cur.fetchall()]
        except Exception:
            cur.execute("""
                SELECT query, results_count, created_at
                FROM search_history
                ORDER BY created_at DESC
                LIMIT 20
            """)
            rows = [dict(r) for r in cur.fetchall()]

        return {
            "ok": True,
            "recent_searches": rows,
        }

    finally:
        cur.close()
        conn.close()


@router.get("/stats")
@limiter.limit("30/minute")
def search_stats(request: Request):
    tenant_id = resolve_tenant_id(getattr(request.state, "tenant_id", None))
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        ensure_tables(cur)
        conn.commit()

        try:
            cur.execute(
                "SELECT COUNT(*) as total FROM pipeline_runs WHERE tenant_id = %s",
                (tenant_id,),
            )
            total_docs = cur.fetchone()["total"]
        except Exception:
            total_docs = 0

        try:
            cur.execute(
                "SELECT COUNT(*) as total FROM bank_transactions WHERE tenant_id = %s",
                (tenant_id,),
            )
            total_txs = cur.fetchone()["total"]
        except Exception:
            total_txs = 0

        try:
            cur.execute("SELECT COUNT(*) as total FROM coa")
            total_coa = cur.fetchone()["total"]
        except Exception:
            total_coa = 0

        try:
            cur.execute(
                "SELECT COUNT(*) as total FROM search_history WHERE tenant_id = %s",
                (tenant_id,),
            )
            total_searches = cur.fetchone()["total"]
        except Exception:
            total_searches = 0

        return {
            "ok": True,
            "indexed": {
                "documents": total_docs,
                "transactions": total_txs,
                "coa_accounts": total_coa,
                "total": total_docs + total_txs + total_coa,
            },
            "total_searches": total_searches,
        }

    finally:
        cur.close()
        conn.close()
