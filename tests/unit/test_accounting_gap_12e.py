"""tests/unit/test_accounting_gap_12e.py — Task 12E: Tax Filing-Grade Validation.

Covers:
  1. check_balance — balanced / unbalanced journals
  2. check_account_codes — valid / invalid / blank codes
  3. check_vat_direction — 3310 credit-only, 3311 debit-only
  4. check_cit_math — 15/85 gross-up
  5. check_vat_math — 18% ratio
  6. check_no_zero_lines
  7. validate_journal — composite, returns valid=True/False + errors list
  8. Service importable with correct exports
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _line(code, debit=0.0, credit=0.0):
    return {"account_code": code, "debit": debit, "credit": credit}


# ---------------------------------------------------------------------------
# 1. check_balance
# ---------------------------------------------------------------------------
class TestCheckBalance:
    def test_balanced_no_errors(self):
        from app.api.services.tax_filing_validator import check_balance
        lines = [_line("1120", debit=100), _line("6110", credit=100)]
        assert check_balance(lines) == []

    def test_unbalanced_returns_error(self):
        from app.api.services.tax_filing_validator import check_balance
        lines = [_line("1120", debit=100), _line("6110", credit=90)]
        errors = check_balance(lines)
        assert len(errors) == 1
        assert errors[0]["rule"] == "BALANCE"

    def test_tolerance_within_half_cent(self):
        from app.api.services.tax_filing_validator import check_balance
        lines = [_line("1120", debit=100.001), _line("6110", credit=100.000)]
        assert check_balance(lines) == []

    def test_empty_lines_balanced(self):
        from app.api.services.tax_filing_validator import check_balance
        assert check_balance([]) == []


# ---------------------------------------------------------------------------
# 2. check_account_codes
# ---------------------------------------------------------------------------
class TestCheckAccountCodes:
    def test_valid_code_no_error(self):
        from app.api.services.tax_filing_validator import check_account_codes
        assert check_account_codes([_line("1110")]) == []

    def test_invalid_code_returns_error(self):
        from app.api.services.tax_filing_validator import check_account_codes
        errors = check_account_codes([_line("9999")])
        assert len(errors) == 1
        assert errors[0]["rule"] == "ACCOUNT_CODE"
        assert errors[0]["account_code"] == "9999"

    def test_blank_code_returns_error(self):
        from app.api.services.tax_filing_validator import check_account_codes
        errors = check_account_codes([{"account_code": "", "debit": 0, "credit": 100}])
        assert len(errors) == 1

    def test_multiple_invalid_codes(self):
        from app.api.services.tax_filing_validator import check_account_codes
        errors = check_account_codes([_line("0000"), _line("8888")])
        assert len(errors) == 2

    def test_all_unified_accounts_valid(self):
        from app.api.services.tax_filing_validator import check_account_codes
        from app.api.services.accounting_rules_core import UNIFIED_ACCOUNTS
        lines = [_line(code, debit=1) for code in UNIFIED_ACCOUNTS.values()]
        assert check_account_codes(lines) == []


# ---------------------------------------------------------------------------
# 3. check_vat_direction
# ---------------------------------------------------------------------------
class TestCheckVatDirection:
    def test_3310_credit_is_ok(self):
        from app.api.services.tax_filing_validator import check_vat_direction
        assert check_vat_direction([_line("3310", credit=18)]) == []

    def test_3310_debit_is_error(self):
        from app.api.services.tax_filing_validator import check_vat_direction
        errors = check_vat_direction([_line("3310", debit=18)])
        assert len(errors) == 1
        assert errors[0]["rule"] == "VAT_DIRECTION"

    def test_3311_debit_is_ok(self):
        from app.api.services.tax_filing_validator import check_vat_direction
        assert check_vat_direction([_line("3311", debit=18)]) == []

    def test_3311_credit_is_error(self):
        from app.api.services.tax_filing_validator import check_vat_direction
        errors = check_vat_direction([_line("3311", credit=18)])
        assert len(errors) == 1
        assert errors[0]["rule"] == "VAT_DIRECTION"

    def test_non_vat_account_no_error(self):
        from app.api.services.tax_filing_validator import check_vat_direction
        assert check_vat_direction([_line("1120", debit=100)]) == []


# ---------------------------------------------------------------------------
# 4. check_cit_math
# ---------------------------------------------------------------------------
class TestCheckCitMath:
    def test_correct_cit_no_error(self):
        from app.api.services.tax_filing_validator import check_cit_math
        # dividend_base=850, expected CIT = 850 / 0.85 * 0.15 = 150
        lines = [
            _line("3370", credit=850),
            _line("3340", credit=150),
        ]
        assert check_cit_math(lines) == []

    def test_wrong_cit_returns_error(self):
        from app.api.services.tax_filing_validator import check_cit_math
        lines = [
            _line("3370", credit=850),
            _line("3340", credit=100),   # wrong — should be 150
        ]
        errors = check_cit_math(lines)
        assert len(errors) == 1
        assert errors[0]["rule"] == "CIT_MATH"

    def test_no_cit_line_skips_check(self):
        from app.api.services.tax_filing_validator import check_cit_math
        assert check_cit_math([_line("1120", debit=100)]) == []

    def test_tolerance_50_cents(self):
        from app.api.services.tax_filing_validator import check_cit_math
        # CIT should be 150, allow up to 0.05 difference
        lines = [
            _line("3370", credit=850),
            _line("3340", credit=150.04),
        ]
        assert check_cit_math(lines) == []


# ---------------------------------------------------------------------------
# 5. check_vat_math
# ---------------------------------------------------------------------------
class TestCheckVatMath:
    def test_correct_vat_no_error(self):
        from app.api.services.tax_filing_validator import check_vat_math
        # revenue=1000, expected VAT = 180
        lines = [
            _line("6110", credit=1000),
            _line("3310", credit=180),
        ]
        assert check_vat_math(lines) == []

    def test_wrong_vat_returns_error(self):
        from app.api.services.tax_filing_validator import check_vat_math
        lines = [
            _line("6110", credit=1000),
            _line("3310", credit=200),   # wrong — should be 180
        ]
        errors = check_vat_math(lines)
        assert len(errors) == 1
        assert errors[0]["rule"] == "VAT_MATH"

    def test_no_vat_line_skips_check(self):
        from app.api.services.tax_filing_validator import check_vat_math
        assert check_vat_math([_line("6110", credit=1000)]) == []

    def test_service_revenue_6120_also_checked(self):
        from app.api.services.tax_filing_validator import check_vat_math
        lines = [
            _line("6120", credit=500),
            _line("3310", credit=90),    # 500 * 0.18 = 90
        ]
        assert check_vat_math(lines) == []


# ---------------------------------------------------------------------------
# 6. check_no_zero_lines
# ---------------------------------------------------------------------------
class TestCheckNoZeroLines:
    def test_normal_lines_ok(self):
        from app.api.services.tax_filing_validator import check_no_zero_lines
        assert check_no_zero_lines([_line("1120", debit=100)]) == []

    def test_zero_line_returns_error(self):
        from app.api.services.tax_filing_validator import check_no_zero_lines
        errors = check_no_zero_lines([_line("1120", debit=0, credit=0)])
        assert len(errors) == 1
        assert errors[0]["rule"] == "ZERO_LINE"


# ---------------------------------------------------------------------------
# 7. validate_journal (composite)
# ---------------------------------------------------------------------------
class TestValidateJournal:
    def test_valid_simple_journal(self):
        from app.api.services.tax_filing_validator import validate_journal
        lines = [
            _line("1120", debit=1000),
            _line("6110", credit=1000),
        ]
        result = validate_journal(lines)
        assert result["valid"] is True
        assert result["error_count"] == 0
        assert result["total_debit"] == 1000.0
        assert result["total_credit"] == 1000.0

    def test_invalid_journal_returns_errors(self):
        from app.api.services.tax_filing_validator import validate_journal
        lines = [
            _line("1120", debit=1000),
            _line("6110", credit=900),   # unbalanced
        ]
        result = validate_journal(lines)
        assert result["valid"] is False
        assert result["error_count"] >= 1

    def test_valid_vat_journal(self):
        from app.api.services.tax_filing_validator import validate_journal
        # 1210 Dr 1180 / 6110 Cr 1000 / 3310 Cr 180
        lines = [
            _line("1210", debit=1180),
            _line("6110", credit=1000),
            _line("3310", credit=180),
        ]
        result = validate_journal(lines)
        assert result["valid"] is True

    def test_cit_journal_valid(self):
        from app.api.services.tax_filing_validator import validate_journal
        # retained_earnings Dr 1000 / dividend_payable Cr 850 / cit_payable Cr 150
        lines = [
            _line("4210", debit=1000),
            _line("3370", credit=850),
            _line("3340", credit=150),
        ]
        result = validate_journal(lines)
        assert result["valid"] is True

    def test_returns_line_count(self):
        from app.api.services.tax_filing_validator import validate_journal
        lines = [_line("1120", debit=100), _line("6110", credit=100)]
        assert validate_journal(lines)["line_count"] == 2

    def test_errors_list_is_present(self):
        from app.api.services.tax_filing_validator import validate_journal
        result = validate_journal([])
        assert "errors" in result
        assert isinstance(result["errors"], list)


# ---------------------------------------------------------------------------
# 8. Service importable
# ---------------------------------------------------------------------------
class TestTaxValidatorImportable:
    def test_module_importable(self):
        import importlib
        mod = importlib.import_module("app.api.services.tax_filing_validator")
        assert hasattr(mod, "validate_journal")
        assert hasattr(mod, "check_balance")
        assert hasattr(mod, "check_account_codes")
        assert hasattr(mod, "check_vat_direction")
        assert hasattr(mod, "check_cit_math")
        assert hasattr(mod, "check_vat_math")
        assert hasattr(mod, "check_no_zero_lines")

    def test_vat_rate_is_18_percent(self):
        from app.api.services.tax_filing_validator import VAT_RATE
        assert VAT_RATE == 0.18

    def test_cit_rate_is_15_percent(self):
        from app.api.services.tax_filing_validator import CIT_RATE
        assert CIT_RATE == 0.15
