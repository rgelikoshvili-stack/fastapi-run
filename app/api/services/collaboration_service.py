"""
app/api/services/collaboration_service.py
Bridge Hub — Collaboration Service
Comments + Assignment draft-ებზე.
Core approval logic არ ეხება.
"""
from typing import Optional
from app.api.db import get_conn, _q


# ========== Comments ==========

async def add_comment(
    draft_id: int,
    comment_text: str,
    author: str = "system",
    author_role: str = "accountant",
    comment_type: str = "note",
    tenant_id: str = "default",
) -> dict:
    if not comment_text or not comment_text.strip():
        return {"ok": False, "error": "კომენტარი ცარიელია"}

    try:
        async with get_conn() as conn:
            exists = await conn.fetchrow(_q(
                "SELECT id FROM journal_drafts WHERE id = %s AND tenant_id = %s"
            ), draft_id, tenant_id)
            if not exists:
                return {"ok": False, "error": "Draft ვერ მოიძებნა"}

            row = dict(await conn.fetchrow(_q("""
                INSERT INTO draft_comments (
                    draft_id, tenant_id, author, author_role,
                    comment_text, comment_type, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                RETURNING id, created_at
            """), draft_id, tenant_id, author, author_role,
                comment_text.strip(), comment_type))

        return {
            "ok": True,
            "comment_id": row["id"],
            "draft_id": draft_id,
            "author": author,
            "author_role": author_role,
            "comment_text": comment_text.strip(),
            "comment_type": comment_type,
            "created_at": str(row["created_at"]),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_comments(draft_id: int, tenant_id: str = "default") -> dict:
    try:
        async with get_conn() as conn:
            rows = [dict(r) for r in await conn.fetch(_q("""
                SELECT id, draft_id, author, author_role,
                       comment_text, comment_type, created_at
                FROM draft_comments
                WHERE draft_id = %s AND tenant_id = %s
                ORDER BY created_at ASC
            """), draft_id, tenant_id)]
        return {"ok": True, "draft_id": draft_id, "count": len(rows), "comments": rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ========== Assignment ==========

async def assign_draft(
    draft_id: int,
    assigned_to: str,
    assigned_by: str = "system",
    priority: str = "normal",
    tenant_id: str = "default",
) -> dict:
    if priority not in ("low", "normal", "high", "urgent"):
        priority = "normal"

    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("""
                UPDATE journal_drafts
                SET assigned_to = %s, assigned_at = NOW(),
                    assigned_by = %s, priority = %s
                WHERE id = %s AND tenant_id = %s
                RETURNING id, assigned_to, assigned_by, assigned_at, priority
            """), assigned_to, assigned_by, priority, draft_id, tenant_id)
            if not row:
                return {"ok": False, "error": "Draft ვერ მოიძებნა"}
            row = dict(row)

        await add_comment(
            draft_id=draft_id,
            comment_text=f"Draft მიენიჭა: {assigned_to} (პრიორიტეტი: {priority})",
            author=assigned_by, author_role="system",
            comment_type="assignment", tenant_id=tenant_id,
        )
        return {
            "ok": True, "draft_id": draft_id,
            "assigned_to": row["assigned_to"],
            "assigned_by": row["assigned_by"],
            "assigned_at": str(row["assigned_at"]),
            "priority": row["priority"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def get_assigned_drafts(
    assigned_to: str,
    tenant_id: str = "default",
    status: Optional[str] = None,
) -> dict:
    try:
        async with get_conn() as conn:
            if status:
                rows = [dict(r) for r in await conn.fetch(_q("""
                    SELECT id, date, description, amount, status,
                           assigned_to, assigned_by, assigned_at, priority
                    FROM journal_drafts
                    WHERE tenant_id = %s AND assigned_to = %s AND status = %s
                    ORDER BY priority DESC, assigned_at DESC
                """), tenant_id, assigned_to, status)]
            else:
                rows = [dict(r) for r in await conn.fetch(_q("""
                    SELECT id, date, description, amount, status,
                           assigned_to, assigned_by, assigned_at, priority
                    FROM journal_drafts
                    WHERE tenant_id = %s AND assigned_to = %s
                    ORDER BY priority DESC, assigned_at DESC
                """), tenant_id, assigned_to)]
        return {"ok": True, "assigned_to": assigned_to, "count": len(rows), "drafts": rows}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def unassign_draft(
    draft_id: int,
    unassigned_by: str = "system",
    tenant_id: str = "default",
) -> dict:
    try:
        async with get_conn() as conn:
            row = await conn.fetchrow(_q("""
                UPDATE journal_drafts
                SET assigned_to = NULL, assigned_at = NULL,
                    assigned_by = NULL, priority = 'normal'
                WHERE id = %s AND tenant_id = %s
                RETURNING id
            """), draft_id, tenant_id)
            if not row:
                return {"ok": False, "error": "Draft ვერ მოიძებნა"}

        await add_comment(
            draft_id=draft_id,
            comment_text="მინიჭება გაუქმდა",
            author=unassigned_by, author_role="system",
            comment_type="assignment", tenant_id=tenant_id,
        )
        return {"ok": True, "draft_id": draft_id, "message": "მინიჭება გაუქმდა"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
