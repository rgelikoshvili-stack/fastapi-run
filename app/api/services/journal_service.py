"""app/api/services/journal_service.py
Journal entry validation utilities.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

_INVALID_CODES = {"", "-", "ETC", "etc", "N/A", "n/a", "None", "null", "undefined"}


def validate_georgian_inn(inn: str) -> bool:
    """9 digits = legal entity, 11 digits = individual/entrepreneur."""
    if not inn:
        return False
    inn = inn.strip()
    return inn.isdigit() and len(inn) in (9, 11)


class JournalEntryValidator:

    @staticmethod
    def validate_account_code(code: Optional[str]) -> bool:
        return bool(code) and code not in _INVALID_CODES

    @staticmethod
    def validate_entry(entry_data: dict) -> bool:
        errors: list[str] = []

        amount = entry_data.get("amount", 0)
        try:
            if float(amount) <= 0:
                errors.append("Amount must be positive")
        except (TypeError, ValueError):
            errors.append("Amount must be a number")

        code = entry_data.get("account_code") or entry_data.get("debit_account") or ""
        if not JournalEntryValidator.validate_account_code(code):
            errors.append("Valid account code required")

        debit_total = entry_data.get("debit_total")
        credit_total = entry_data.get("credit_total")
        if debit_total is not None and credit_total is not None:
            try:
                if round(float(debit_total), 2) != round(float(credit_total), 2):
                    errors.append("Debit/Credit imbalance")
            except (TypeError, ValueError):
                errors.append("Debit/Credit values must be numbers")

        partner_inn = entry_data.get("partner_inn") or entry_data.get("buyer_inn") or ""
        if partner_inn and not validate_georgian_inn(partner_inn):
            errors.append(f"Invalid Georgian INN: {partner_inn}")

        if errors:
            log.debug("JournalEntryValidator.validate_entry failed: %s", errors)
            raise ValueError("; ".join(errors))

        return True
