from typing import List, Dict, Any

from app.api.services.erp_memory_service import upsert_erp_posting_memory


def map_erp_row(row: Dict[str, Any], default_source_system: str = "balance") -> Dict[str, Any]:
    return {
        "source_system": row.get("source_system") or default_source_system,
        "external_entry_id": row.get("external_entry_id"),
        "external_doc_id": row.get("external_doc_id"),
        "doc_type": row.get("doc_type"),
        "description": row.get("description"),
        "partner": row.get("partner"),
        "amount": row.get("amount"),
        "currency": row.get("currency") or "GEL",
        "debit_account": row.get("debit_account"),
        "credit_account": row.get("credit_account"),
        "account_code": row.get("account_code"),
        "direction": row.get("direction"),
        "posting_date": row.get("posting_date"),
    }


def import_erp_history(items: List[Dict[str, Any]], default_source_system: str = "balance") -> Dict[str, Any]:
    processed = 0
    inserted_or_updated = 0
    errors = []

    for idx, item in enumerate(items, start=1):
        try:
            mapped = map_erp_row(item, default_source_system=default_source_system)

            result = upsert_erp_posting_memory(
                source_system=mapped["source_system"],
                external_entry_id=mapped["external_entry_id"],
                external_doc_id=mapped["external_doc_id"],
                doc_type=mapped["doc_type"],
                description=mapped["description"],
                partner=mapped["partner"],
                amount=mapped["amount"],
                currency=mapped["currency"],
                debit_account=mapped["debit_account"],
                credit_account=mapped["credit_account"],
                account_code=mapped["account_code"],
                direction=mapped["direction"],
                posting_date=mapped["posting_date"],
            )

            processed += 1
            if result.get("ok"):
                inserted_or_updated += 1
            else:
                errors.append({"index": idx, "error": "upsert failed", "item": item})

        except Exception as e:
            errors.append({"index": idx, "error": str(e), "item": item})

    return {
        "ok": len(errors) == 0,
        "processed": processed,
        "inserted_or_updated": inserted_or_updated,
        "errors": errors,
    }