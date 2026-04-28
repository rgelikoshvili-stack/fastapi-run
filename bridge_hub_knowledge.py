"""
bridge_hub_knowledge.py — backward-compatibility shim.
All logic lives in app/knowledge/.
"""
from app.knowledge import *  # noqa: F401, F403
from app.knowledge import (
    TAX_RATES, CHART_OF_ACCOUNTS, ACCA_STANDARDS, TAX_RULES,
    _fmt, _jl, _journal, _payload, _CLS_RULES, _KB,
    _load_files, _load_learned, _load_learned_from_db,
    learn_new_rule, migrate_json_to_db,
    get_tax_section, get_accounting_section,
    classify_transaction, search_knowledge, get_context_for_llm,
    build_journal_from_text, get_stats,
    calculate_vat, calculate_payroll, calculate_cit,
    calculate_withholding, calculate_depreciation, calculate_inventory_shortage,
)
