import psycopg2.extras

from app.api.db import get_db


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def save_transaction_memory(description, partner, amount, account_code):
    desc = _norm(description)
    part = _norm(partner)

    if not account_code:
        return {"ok": False, "error": "account_code is required"}

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT id, usage_count
            FROM transaction_memory
            WHERE COALESCE(description, '') = %s
              AND COALESCE(partner, '') = %s
              AND account_code = %s
            LIMIT 1
            """,
            (desc, part, account_code),
        )
        row = cur.fetchone()

        if row:
            cur.execute(
                """
                UPDATE transaction_memory
                SET
                    usage_count = usage_count + 1,
                    last_used_at = NOW(),
                    updated_at = NOW(),
                    amount = %s
                WHERE id = %s
                RETURNING id, usage_count
                """,
                (amount, row["id"]),
            )
            updated = cur.fetchone()
            conn.commit()
            return {
                "ok": True,
                "mode": "updated",
                "id": updated["id"],
                "usage_count": updated["usage_count"],
            }

        cur.execute(
            """
            INSERT INTO transaction_memory (
                description,
                partner,
                amount,
                account_code,
                confidence,
                usage_count,
                last_used_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
            RETURNING id, usage_count
            """,
            (desc, part, amount, account_code, 1.0, 1),
        )
        inserted = cur.fetchone()
        conn.commit()

        return {
            "ok": True,
            "mode": "inserted",
            "id": inserted["id"],
            "usage_count": inserted["usage_count"],
        }

    finally:
        cur.close()
        conn.close()


def find_memory_match(description, partner):
    desc = _norm(description)
    part = _norm(partner)

    if not desc and not part:
        return None

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                id,
                description,
                partner,
                account_code,
                usage_count,
                last_used_at
            FROM transaction_memory
            WHERE
                (
                    %s <> '' AND COALESCE(description, '') = %s
                )
                OR
                (
                    %s <> '' AND COALESCE(partner, '') = %s
                )
            ORDER BY
                CASE
                    WHEN %s <> '' AND %s <> ''
                         AND COALESCE(description, '') = %s
                         AND COALESCE(partner, '') = %s
                    THEN 0
                    WHEN %s <> '' AND COALESCE(description, '') = %s
                    THEN 1
                    WHEN %s <> '' AND COALESCE(partner, '') = %s
                    THEN 2
                    ELSE 3
                END,
                usage_count DESC,
                id DESC
            LIMIT 1
            """,
            (
                desc, desc,
                part, part,
                desc, part, desc, part,
                desc, desc,
                part, part,
            ),
        )
        row = cur.fetchone()

        if not row:
            return None

        usage_count = int(row["usage_count"] or 1)

        confidence = 0.88
        if usage_count >= 5:
            confidence = 0.96
        elif usage_count >= 3:
            confidence = 0.93
        elif usage_count >= 2:
            confidence = 0.90

        return {
            "account_code": row["account_code"],
            "reason": "memory_match",
            "confidence": round(confidence, 2),
            "review_required": confidence < 0.90,
            "status": "drafted" if confidence >= 0.90 else "pending_approval",
            "source": "memory",
            "memory_usage_count": usage_count,
            "memory_description": row["description"],
            "memory_partner": row["partner"],
        }

    finally:
        cur.close()
        conn.close()


def list_transaction_memory(limit: int = 100):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                id,
                description,
                partner,
                amount,
                account_code,
                confidence,
                usage_count,
                last_used_at,
                created_at,
                updated_at
            FROM transaction_memory
            ORDER BY id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        cur.close()
        conn.close()