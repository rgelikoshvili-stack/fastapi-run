"""app/api/services/completeness_checker.py
Document set completeness checker — produces ✅/❌/⚠️ indicators per document type
and generates human-readable alerts for the Approval Queue.

Triangle rule (Georgian standard):
  For a valid purchase transaction you need ALL THREE:
    1. Waybill  (სასაქონლო ზედნადები)
    2. Tax Invoice (ანგარიშ-ფაქტურა)
    3. Commercial Invoice / Act (ინვოისი / მიღება-ჩაბარების აქტი)

  For service contracts:
    1. Contract (ხელშეკრულება)
    2. Act of completion (მიღება-ჩაბარების აქტი)
    3. Tax Invoice (ანგარიშ-ფაქტურა) — if VAT payer

Indicator legend:
  ✅  = present and valid
  ⚠️  = present but with issues (amounts/INNs differ, or date mismatch)
  ❌  = missing or not found
"""
from __future__ import annotations

from typing import Optional


DOC_ICONS = {
    "ok":      "✅",
    "warning": "⚠️",
    "missing": "❌",
}

# Required doc types for each flow
GOODS_FLOW    = ("waybill", "tax_invoice", "invoice")
SERVICE_FLOW  = ("contract", "act", "tax_invoice")
ANY_FLOW      = ("tax_invoice", "invoice", "waybill", "contract", "act", "delivery")


def _icon(status: str) -> str:
    return DOC_ICONS.get(status, "❌")


def check_document_set(
    pipeline_docs: list[dict],
    match_result: Optional[dict] = None,
    flow: str = "auto",  # "goods", "service", "auto"
) -> dict:
    """
    pipeline_docs: list of dicts, each with at minimum:
        {"doc_type": str, "doc_number": str|None, "total_amount": float|None,
         "seller_inn": str|None, "buyer_inn": str|None, "issue_date": str|None}
    match_result: output from triangle_matcher.compute_match_score (optional)
    flow: "goods" | "service" | "auto"

    Returns:
    {
      "flow":      "goods" | "service",
      "summary":   "✅ Complete" | "⚠️ Incomplete" | "❌ Missing documents",
      "score":     0.0–1.0,
      "indicators": {
          "waybill":    {"status": "ok|warning|missing", "icon": "✅", "doc_number": ..., "amount": ...},
          "tax_invoice": {...},
          "invoice":    {...},
          ...
      },
      "alerts":    [str],   # human-readable warnings
      "ready_to_post": bool,
    }
    """
    doc_map: dict[str, list[dict]] = {}
    for d in pipeline_docs:
        dt = d.get("doc_type", "unknown")
        doc_map.setdefault(dt, []).append(d)

    alerts: list[str] = []

    # Auto-detect flow
    if flow == "auto":
        if "waybill" in doc_map or "delivery" in doc_map:
            flow = "goods"
        elif "contract" in doc_map or "act" in doc_map:
            flow = "service"
        else:
            flow = "goods"  # default assumption

    required = GOODS_FLOW if flow == "goods" else SERVICE_FLOW
    indicators: dict[str, dict] = {}

    for doc_type in required:
        docs = doc_map.get(doc_type, [])
        if not docs:
            indicators[doc_type] = {
                "status":     "missing",
                "icon":       _icon("missing"),
                "doc_number": None,
                "amount":     None,
                "issue_date": None,
            }
            label_map = {
                "waybill":    "სასაქონლო ზედნადები",
                "tax_invoice":"ანგარიშ-ფაქტურა",
                "invoice":    "ინვოისი",
                "contract":   "ხელშეკრულება",
                "act":        "მიღება-ჩაბარების აქტი",
                "delivery":   "მიწოდება",
            }
            alerts.append(f"❌ {label_map.get(doc_type, doc_type)} — არ არის")
        else:
            d = docs[0]
            status = "ok"
            doc_alerts = []

            # Check against match_result mismatches
            if match_result:
                mismatches = match_result.get("mismatches", [])
                if f"amount_mismatch" in mismatches:
                    status = "warning"
                    doc_alerts.append(f"⚠️ {doc_type}: თანხა არ ემთხვევა")
                if f"seller_inn_mismatch" in mismatches and doc_type in ("waybill", "tax_invoice"):
                    status = "warning"
                    doc_alerts.append(f"⚠️ {doc_type}: გამყიდველის ID.კ. არ ემთხვევა")
                if f"buyer_inn_mismatch" in mismatches and doc_type in ("waybill", "tax_invoice"):
                    status = "warning"
                    doc_alerts.append(f"⚠️ {doc_type}: მყიდველის ID.კ. არ ემთხვევა")

            indicators[doc_type] = {
                "status":     status,
                "icon":       _icon(status),
                "doc_number": d.get("doc_number") or d.get("document_number"),
                "amount":     d.get("total_amount") or d.get("total_with_vat"),
                "issue_date": d.get("issue_date"),
                "seller_inn": d.get("seller_inn"),
                "buyer_inn":  d.get("buyer_inn"),
            }
            alerts.extend(doc_alerts)

    # Amount cross-check across present docs
    amounts = []
    for doc_type, ind in indicators.items():
        if ind["status"] != "missing" and ind.get("amount"):
            amounts.append((doc_type, float(ind["amount"])))

    if len(amounts) >= 2:
        base_amt = amounts[0][1]
        for dt, amt in amounts[1:]:
            if abs(amt - base_amt) > 0.10:
                alerts.append(f"⚠️ თანხები არ ემთხვევა: {amounts[0][0]}={base_amt}, {dt}={amt}")
                for doc_type in indicators:
                    if indicators[doc_type]["status"] == "ok":
                        indicators[doc_type]["status"] = "warning"
                        indicators[doc_type]["icon"] = _icon("warning")

    missing_count  = sum(1 for v in indicators.values() if v["status"] == "missing")
    warning_count  = sum(1 for v in indicators.values() if v["status"] == "warning")
    total_required = len(required)

    if missing_count == 0 and warning_count == 0:
        summary = "✅ სრული"
        score   = 1.0
    elif missing_count == 0:
        summary = "⚠️ საჭიროებს შემოწმებას"
        score   = 0.7
    elif missing_count < total_required:
        summary = "⚠️ არასრული"
        score   = round(1 - missing_count / total_required, 2)
    else:
        summary = "❌ დოკუმენტები აკლია"
        score   = 0.0

    ready_to_post = missing_count == 0 and warning_count == 0

    # Match score override
    if match_result and match_result.get("score", 0) >= 0.8 and missing_count == 0:
        ready_to_post = True
        summary = "✅ სრული"
        score   = match_result["score"]

    return {
        "flow":          flow,
        "summary":       summary,
        "score":         score,
        "indicators":    indicators,
        "alerts":        alerts,
        "ready_to_post": ready_to_post,
        "missing_count": missing_count,
        "warning_count": warning_count,
    }


def build_approval_matrix(pipeline_run: dict, related_docs: list[dict]) -> dict:
    """
    High-level helper called from the approval route.
    pipeline_run: row from pipeline_runs table
    related_docs: all processed_documents linked to this draft

    Returns a matrix dict ready to be embedded in the approval queue card.
    """
    # Build pipeline_docs list from related docs
    pipeline_docs = []
    for rd in related_docs:
        extraction = rd.get("extraction") or {}
        if isinstance(extraction, str):
            import json
            try:
                extraction = json.loads(extraction)
            except Exception:
                extraction = {}

        pipeline_docs.append({
            "doc_type":      extraction.get("document_type") or rd.get("doc_type") or "unknown",
            "doc_number":    extraction.get("document_number"),
            "total_amount":  extraction.get("total_amount") or extraction.get("total_with_vat"),
            "seller_inn":    extraction.get("seller_inn") or (extraction.get("seller") or {}).get("inn"),
            "buyer_inn":     extraction.get("buyer_inn") or (extraction.get("buyer") or {}).get("inn"),
            "issue_date":    extraction.get("issue_date"),
        })

    # Also include the primary document from the pipeline run
    primary_extraction = pipeline_run.get("extraction") or {}
    if isinstance(primary_extraction, str):
        import json
        try:
            primary_extraction = json.loads(primary_extraction)
        except Exception:
            primary_extraction = {}

    if primary_extraction.get("document_type"):
        pipeline_docs.append({
            "doc_type":     primary_extraction.get("document_type"),
            "doc_number":   primary_extraction.get("document_number"),
            "total_amount": primary_extraction.get("total_amount") or primary_extraction.get("total_with_vat"),
            "seller_inn":   primary_extraction.get("seller_inn"),
            "buyer_inn":    primary_extraction.get("buyer_inn"),
            "issue_date":   primary_extraction.get("issue_date"),
        })

    result = check_document_set(pipeline_docs, flow="auto")
    return result
