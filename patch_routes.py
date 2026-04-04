with open("app/api/routes_transaction_ai.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. llm_cost და vat ინფო result-ში
old = '        result["explanation"] = _build_explanation(result)\n        result["tenant_id"] = tenant_id'
new = '        result["explanation"] = _build_explanation(result)\n        result["tenant_id"] = tenant_id\n        result["llm_cost"] = result.get("llm_cost", 0.0)\n        result["vat_info"] = {"suggested": result.get("vat_suggested", False), "amount": result.get("vat_amount"), "payg_required": result.get("payg_required", False), "payg_amount": result.get("payg_amount")}'
content = content.replace(old, new, 1)

with open("app/api/routes_transaction_ai.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Done!")
