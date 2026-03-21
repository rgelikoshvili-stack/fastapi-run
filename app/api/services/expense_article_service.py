import psycopg2.extras

from app.api.db import get_db


def _norm(value):
    return " ".join(str(value or "").strip().lower().split())


def list_expense_articles(active_only: bool = False, limit: int = 200):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        if active_only:
            cur.execute(
                """
                SELECT
                    id,
                    article_code,
                    article_name,
                    parent_code,
                    linked_account_code,
                    category,
                    keywords,
                    description,
                    is_active,
                    source_system,
                    synced_at,
                    created_at,
                    updated_at
                FROM expense_articles_cache
                WHERE is_active = TRUE
                ORDER BY article_name ASC
                LIMIT %s
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT
                    id,
                    article_code,
                    article_name,
                    parent_code,
                    linked_account_code,
                    category,
                    keywords,
                    description,
                    is_active,
                    source_system,
                    synced_at,
                    created_at,
                    updated_at
                FROM expense_articles_cache
                ORDER BY article_name ASC
                LIMIT %s
                """,
                (limit,),
            )

        return [dict(row) for row in cur.fetchall()]

    finally:
        cur.close()
        conn.close()


def get_expense_article(article_code: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        cur.execute(
            """
            SELECT
                id,
                article_code,
                article_name,
                parent_code,
                linked_account_code,
                category,
                keywords,
                description,
                is_active,
                source_system,
                raw_payload,
                synced_at,
                created_at,
                updated_at
            FROM expense_articles_cache
            WHERE article_code = %s
            LIMIT 1
            """,
            (article_code,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    finally:
        cur.close()
        conn.close()


def search_expense_articles(query: str, active_only: bool = False, limit: int = 50):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        q = f"%{(query or '').strip()}%"

        if active_only:
            cur.execute(
                """
                SELECT
                    id,
                    article_code,
                    article_name,
                    parent_code,
                    linked_account_code,
                    category,
                    keywords,
                    description,
                    is_active,
                    source_system,
                    synced_at,
                    created_at,
                    updated_at
                FROM expense_articles_cache
                WHERE is_active = TRUE
                  AND (
                        article_code ILIKE %s
                     OR article_name ILIKE %s
                     OR COALESCE(category, '') ILIKE %s
                     OR COALESCE(keywords, '') ILIKE %s
                     OR COALESCE(description, '') ILIKE %s
                     OR COALESCE(linked_account_code, '') ILIKE %s
                  )
                ORDER BY article_name ASC
                LIMIT %s
                """,
                (q, q, q, q, q, q, limit),
            )
        else:
            cur.execute(
                """
                SELECT
                    id,
                    article_code,
                    article_name,
                    parent_code,
                    linked_account_code,
                    category,
                    keywords,
                    description,
                    is_active,
                    source_system,
                    synced_at,
                    created_at,
                    updated_at
                FROM expense_articles_cache
                WHERE
                      article_code ILIKE %s
                   OR article_name ILIKE %s
                   OR COALESCE(category, '') ILIKE %s
                   OR COALESCE(keywords, '') ILIKE %s
                   OR COALESCE(description, '') ILIKE %s
                   OR COALESCE(linked_account_code, '') ILIKE %s
                ORDER BY article_name ASC
                LIMIT %s
                """,
                (q, q, q, q, q, q, limit),
            )

        return [dict(row) for row in cur.fetchall()]

    finally:
        cur.close()
        conn.close()


def upsert_expense_article(article: dict):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        article_code = (article.get("article_code") or "").strip()
        article_name = (article.get("article_name") or "").strip()

        if not article_code:
            return {"ok": False, "error": "article_code is required"}
        if not article_name:
            return {"ok": False, "error": "article_name is required"}

        cur.execute(
            """
            INSERT INTO expense_articles_cache (
                article_code,
                article_name,
                parent_code,
                linked_account_code,
                category,
                keywords,
                description,
                is_active,
                source_system,
                raw_payload,
                synced_at,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW()
            )
            ON CONFLICT (article_code)
            DO UPDATE SET
                article_name = EXCLUDED.article_name,
                parent_code = EXCLUDED.parent_code,
                linked_account_code = EXCLUDED.linked_account_code,
                category = EXCLUDED.category,
                keywords = EXCLUDED.keywords,
                description = EXCLUDED.description,
                is_active = EXCLUDED.is_active,
                source_system = EXCLUDED.source_system,
                raw_payload = EXCLUDED.raw_payload,
                synced_at = NOW(),
                updated_at = NOW()
            RETURNING id, article_code, article_name
            """,
            (
                article_code,
                article_name,
                article.get("parent_code"),
                article.get("linked_account_code"),
                article.get("category"),
                article.get("keywords"),
                article.get("description"),
                bool(article.get("is_active", True)),
                article.get("source_system") or "manual",
                psycopg2.extras.Json(article.get("raw_payload")) if article.get("raw_payload") is not None else None,
            ),
        )

        row = cur.fetchone()
        conn.commit()

        return {
            "ok": True,
            "article": dict(row) if row else None,
        }

    finally:
        cur.close()
        conn.close()


def bulk_upsert_expense_articles(articles: list[dict]):
    inserted_or_updated = 0
    errors = []

    for idx, article in enumerate(articles, start=1):
        try:
            result = upsert_expense_article(article)
            if result.get("ok"):
                inserted_or_updated += 1
            else:
                errors.append({"index": idx, "error": result.get("error")})
        except Exception as e:
            errors.append({"index": idx, "error": str(e)})

    return {
        "ok": len(errors) == 0,
        "processed": len(articles),
        "inserted_or_updated": inserted_or_updated,
        "errors": errors,
    }


def find_expense_article(description: str = "", partner: str = ""):
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
                article_code,
                article_name,
                parent_code,
                linked_account_code,
                category,
                keywords,
                description,
                is_active,
                source_system
            FROM expense_articles_cache
            WHERE is_active = TRUE
            ORDER BY id DESC
            """
        )
        rows = cur.fetchall()

        best = None
        best_score = 0

        for row in rows:
            article_name = _norm(row.get("article_name"))
            keywords = _norm(row.get("keywords"))
            article_desc = _norm(row.get("description"))
            linked_account_code = row.get("linked_account_code")

            if not linked_account_code:
                continue

            score = 0

            if article_name and desc and article_name in desc:
                score += 5
            if article_name and part and article_name in part:
                score += 4

            if keywords:
                for kw in [x.strip() for x in keywords.split(",") if x.strip()]:
                    if desc and kw in desc:
                        score += 3
                    if part and kw in part:
                        score += 2

            if article_desc and desc and article_desc in desc:
                score += 2

            if score > best_score:
                best_score = score
                best = dict(row)

        if best_score <= 0:
            return None

        return best

    finally:
        cur.close()
        conn.close()