"""app/api/services/posting_helpers.py

Pure decimal and journal-line utilities extracted from posting_service.py.
No DB access, no side effects.

All symbols are re-exported by posting_service.py — existing imports work unchanged.
"""
import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, List

log = logging.getLogger(__name__)


def _to_decimal(v) -> Decimal:
    """Safely convert any numeric value to Decimal for financial calculations."""
    if isinstance(v, Decimal):
        return v
    if v is None:
        return Decimal("0")
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0")


def _sum_debits(lines: List[dict]) -> Decimal:
    return sum((_to_decimal(x.get("debit", 0)) for x in lines), Decimal("0"))


def _sum_credits(lines: List[dict]) -> Decimal:
    return sum((_to_decimal(x.get("credit", 0)) for x in lines), Decimal("0"))


def _derive_amount_from_lines(lines: List[dict]) -> Decimal:
    return max(_sum_debits(lines), _sum_credits(lines))


def _normalize_lines(lines: Any) -> List[dict]:
    result: List[dict] = []

    if not lines:
        return result

    if isinstance(lines, str):
        text = lines.strip()
        if not text:
            return result
        try:
            parsed = json.loads(text)
            return _normalize_lines(parsed)
        except Exception:
            return result

    if isinstance(lines, list):
        for line in lines:
            if isinstance(line, dict):
                result.append(
                    {
                        "account_code": str(line.get("account_code", "")).strip(),
                        "label": line.get("label", ""),
                        "debit": float(_to_decimal(line.get("debit", 0) or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                        "credit": float(_to_decimal(line.get("credit", 0) or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                    }
                )
            elif isinstance(line, (list, tuple)) and len(line) >= 3:
                account_code, debit, credit = line[:3]
                result.append(
                    {
                        "account_code": str(account_code).strip(),
                        "label": "",
                        "debit": float(_to_decimal(debit or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                        "credit": float(_to_decimal(credit or 0).quantize(Decimal("0.01"), ROUND_HALF_UP)),
                    }
                )

    return result


def _validate_lines(lines: List[dict]):
    """Return an error string if the journal lines are invalid, else None."""
    if not lines:
        return "journal lines აკლია"

    for idx, line in enumerate(lines, start=1):
        if not line.get("account_code"):
            return f"line #{idx}: account_code აკლია"

        debit = _to_decimal(line.get("debit", 0) or 0)
        credit = _to_decimal(line.get("credit", 0) or 0)

        if debit < 0 or credit < 0:
            return f"line #{idx}: debit/credit უარყოფითი ვერ იქნება"

        if debit == 0 and credit == 0:
            return f"line #{idx}: debit ან credit უნდა ჰქონდეს"

        if debit > 0 and credit > 0:
            return f"line #{idx}: ერთ ხაზზე debit და credit ერთად არ შეიძლება"

    debit_total = _sum_debits(lines)
    credit_total = _sum_credits(lines)

    dt = debit_total.quantize(Decimal("0.01"), ROUND_HALF_UP)
    ct = credit_total.quantize(Decimal("0.01"), ROUND_HALF_UP)
    if dt != ct:
        return f"დებეტი და კრედიტი არ ემთხვევა (Dr={dt}, Cr={ct})"

    return None
