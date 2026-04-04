import re

with open("app/api/transaction_classifier.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. imports
old = "from app.api.services.erp_memory_service import find_erp_memory_match"
new = """from app.api.services.erp_memory_service import find_erp_memory_match
from app.policy.localization import georgia_pack
import app.api.services.llm_service as llm_service"""
content = content.replace(old, new, 1)

# 2. llm fallback
old = """        if paid_in_value is not None and paid_out_value is None:
            matched_account = "6100"
            matched_reason = "income_direction"
            confidence = 0.65
        elif paid_out_value is not None and paid_in_value is None:
            matched_account = "7190"
            matched_reason = "expense_direction"
            confidence = 0.55
        else:
            matched_account = "7190"
            matched_reason = "default_expense"
            confidence = 0.4"""
new = """        try:
            llm_result = llm_service.classify(
                description, {"partner": part, "amount": amount_for_history}, tenant_id
            )
            if llm_result.get("account_code") and float(llm_result.get("confidence", 0)) > 0.55:
                matched_account = llm_result["account_code"]
                matched_reason  = "llm:gpt"
                confidence      = float(llm_result["confidence"])
                keyword_matched = True
            else:
                raise ValueError("low confidence")
        except Exception:
            if paid_in_value is not None and paid_out_value is None:
                matched_account = "6100"
                matched_reason = "income_direction"
                confidence = 0.65
            elif paid_out_value is not None and paid_in_value is None:
                matched_account = "7190"
                matched_reason = "expense_direction"
                confidence = 0.55
            else:
                matched_account = "7190"
                matched_reason = "default_expense"
                confidence = 0.4"""
content = content.replace(old, new, 1)

# 3. georgia_pack enrichment
old = """    confidence = round(min(confidence, 1.0), 2)
    review_required = confidence < 0.75
    anomaly = check_anomaly(amount_for_history, matched_account, tenant_id)"""
new = """    confidence = round(min(confidence, 1.0), 2)
    review_required = confidence < 0.75
    anomaly = check_anomaly(amount_for_history, matched_account, tenant_id)
    georgia_enriched = georgia_pack.apply_rules(
        {"description": description, "amount": amount_for_history or 0,
         "account_code": matched_account}, tenant_id
    )"""
content = content.replace(old, new, 1)

# 4. final return
old = """        "autopilot_reason": "rules_path",
        "anomaly_flag": anomaly.get("anomaly_flag", False),
        "anomaly_reason": anomaly.get("anomaly_reason"),
    }"""
new = """        "autopilot_reason": "rules_path",
        "anomaly_flag": anomaly.get("anomaly_flag", False),
        "anomaly_reason": anomaly.get("anomaly_reason"),
        "vat_suggested": georgia_enriched.get("vat_suggested", False),
        "vat_amount": georgia_enriched.get("vat_amount"),
        "payg_required": georgia_enriched.get("payg_required", False),
        "payg_amount": georgia_enriched.get("payg_amount"),
    }"""
content = content.replace(old, new, 1)

with open("app/api/transaction_classifier.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done!")
