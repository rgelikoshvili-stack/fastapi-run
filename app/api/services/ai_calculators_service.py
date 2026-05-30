"""
app/api/services/ai_calculators_service.py

Calculator wrappers and stats helpers extracted from ai_chat_service.py.
Called by routes_ai.py (and routes_payroll.py for tax calcs).
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


# ── Knowledge Base ────────────────────────────────────────────────────────────
try:
    from app.knowledge import (
        calculate_vat,
        calculate_payroll,
        calculate_cit,
        calculate_depreciation,
        classify_transaction,
        search_knowledge,
        learn_new_rule,
        get_stats,
        CHART_OF_ACCOUNTS,
    )
    KB_LOADED = True
except ImportError:
    KB_LOADED = False
    CHART_OF_ACCOUNTS = {}


# ── Vector DB ─────────────────────────────────────────────────────────────────
_vector_db_available = False
try:
    from bridge_hub_vector_db import (
        hybrid_search,
        learn_from_correction,
        get_vector_stats,
        index_files,
    )
    _vector_db_available = True
except ImportError:
    pass  # optional dependency


# ── Accounting Rules ──────────────────────────────────────────────────────────
try:
    from app.api.services.accounting_rules import (
        build_vat_posting,
        build_vat_posting_from_net,
        build_dividend_posting,
        build_payroll_posting,
        build_payroll_from_net_posting,
    )
    ACCT_RULES_LOADED = True
except ImportError:
    ACCT_RULES_LOADED = False


# ── Public functions ──────────────────────────────────────────────────────────

def get_ai_system_stats():
    result = {
        "kb_loaded": KB_LOADED,
        "vector_db_available": _vector_db_available,
        "accounting_rules_loaded": ACCT_RULES_LOADED,
    }
    if KB_LOADED:
        result["knowledge_base"] = get_stats()
    return result


def run_ai_search(q: str, top_k: int = 5, use_vector: bool = True):
    if use_vector and _vector_db_available:
        try:
            return {"query": q, "results": hybrid_search(q, top_k), "method": "hybrid"}
        except Exception as e:
            log.warning("unexpected error: %s", e)

    if KB_LOADED:
        return {"query": q, "results": search_knowledge(q, top_k), "method": "keyword"}

    return {"query": q, "results": [], "method": "unavailable"}


def run_vat_calc(request):
    payment_status = getattr(request, "payment_status", "paid") or "paid"
    inclusive = bool(getattr(request, "inclusive", True))
    service_type = getattr(request, "service_type", "standard") or "standard"

    if ACCT_RULES_LOADED:
        if inclusive:
            return build_vat_posting(request.amount, payment_status=payment_status)
        return build_vat_posting_from_net(request.amount, payment_status=payment_status)

    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_vat(request.amount, inclusive, service_type)


def run_dividend_calc(request):
    if ACCT_RULES_LOADED:
        return build_dividend_posting(request.gross_amount, request.cit_rate)

    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_cit(request.gross_amount)


def run_payroll_calc(request):
    if ACCT_RULES_LOADED:
        mode = request.mode or "gross"
        pension = 0.02 if getattr(request, "include_employee_payg", True) else 0.0
        if mode == "net":
            return build_payroll_from_net_posting(
                request.gross,
                employee_pension_rate=pension,
                employer_pension_rate=pension,
            )
        return build_payroll_posting(
            request.gross,
            employee_pension_rate=pension,
            employer_pension_rate=pension,
        )

    if not KB_LOADED:
        return {"error": "KB not loaded"}

    return calculate_payroll(request.gross, request.include_employee_payg, request.mode or "gross")


def run_cit_calc(request):
    if not KB_LOADED:
        return {"error": "KB not loaded"}
    return calculate_cit(request.distributed_profit)


def run_depreciation_calc(request):
    if not KB_LOADED:
        return {"error": "KB not loaded"}
    return calculate_depreciation(request.cost, request.residual, request.useful_life_years, request.method)


def run_classify_tx(request):
    if not KB_LOADED:
        return {"error": "KB not loaded"}

    from app.api.services.classification_explanation_service import build_explanation
    result = classify_transaction(request.description, request.tenant_id)
    enriched = build_explanation(result)
    return {
        **enriched,
        "account_type": CHART_OF_ACCOUNTS.get(
            result.get("account") or result.get("account_code"), {}
        ).get("type", "unknown"),
    }


async def run_learn_rule(request):
    if not KB_LOADED:
        return {"status": "error", "message": "KB not loaded"}

    results = {
        "python_rules": await learn_new_rule(request.pattern, request.account, request.tenant_id, request.note)
    }

    if request.use_vector and _vector_db_available:
        try:
            results["vector_db"] = learn_from_correction(
                request.pattern, request.account,
                tenant_id=request.tenant_id, note=request.note,
            )
        except Exception as e:
            results["vector_db"] = {"status": "error", "error": str(e)}

    account_name = CHART_OF_ACCOUNTS.get(request.account, {}).get("name", request.account)
    return {
        "status": "learned",
        "message": f"✅ ვისწავლე: '{request.pattern}' → {request.account} ({account_name})",
        "stored_in": list(results.keys()),
    }


def run_index_files(request):
    if not _vector_db_available:
        return {"status": "error", "detail": "ChromaDB არ არის"}
    stats = index_files(request.files_dir, request.force_reindex)
    return {"status": "success", **stats}


def run_vector_stats():
    if not _vector_db_available:
        return {"available": False}
    try:
        return {"available": True, **get_vector_stats()}
    except Exception as e:
        return {"available": True, "error": str(e)}
