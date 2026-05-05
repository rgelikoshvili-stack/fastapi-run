from fastapi import APIRouter, Query, Body

from app.api.response_utils import ok_response, error_response
from app.api.authz import require_permission
from app.api.services.expense_article_service import (
    list_expense_articles,
    get_expense_article,
    search_expense_articles,
    upsert_expense_article,
    bulk_upsert_expense_articles,
)

router = APIRouter(prefix="/expense-articles", tags=["expense-articles"])


@router.get("/list")
def expense_articles_list(
    active_only: bool = Query(False),
    limit: int = Query(200, ge=1, le=1000),
):
    try:
        rows = list_expense_articles(active_only=active_only, limit=limit)
        return ok_response("Expense articles list", {"items": rows, "count": len(rows)})
    except Exception as e:
        return error_response("List failed", "EXPENSE_ARTICLES_LIST_ERROR", str(e))


@router.get("/get/{article_code}")
def expense_articles_get(article_code: str):
    try:
        row = get_expense_article(article_code)
        if not row:
            return error_response("Not found", "NOT_FOUND", f"Expense article not found: {article_code}")
        return ok_response("Expense article found", row)
    except Exception as e:
        return error_response("Get failed", "EXPENSE_ARTICLES_GET_ERROR", str(e))


@router.get("/search")
def expense_articles_search(
    q: str = Query(..., min_length=1),
    active_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=500),
):
    try:
        rows = search_expense_articles(query=q, active_only=active_only, limit=limit)
        return ok_response("Expense articles search", {"items": rows, "count": len(rows)})
    except Exception as e:
        return error_response("Search failed", "EXPENSE_ARTICLES_SEARCH_ERROR", str(e))


@router.post("/upsert")
def expense_articles_upsert(payload: dict = Body(...)):
    try:
        result = upsert_expense_article(payload)
        if not result.get("ok"):
            return error_response("Upsert failed", "EXPENSE_ARTICLES_UPSERT_ERROR", result.get("error"))
        return ok_response("Expense article upserted", result)
    except Exception as e:
        return error_response("Upsert failed", "EXPENSE_ARTICLES_UPSERT_ERROR", str(e))


@router.post("/bulk-upsert")
def expense_articles_bulk_upsert(payload: list[dict] = Body(...)):
    try:
        result = bulk_upsert_expense_articles(payload)
        return ok_response("Expense articles bulk upsert finished", result)
    except Exception as e:
        return error_response("Bulk upsert failed", "EXPENSE_ARTICLES_BULK_UPSERT_ERROR", str(e))