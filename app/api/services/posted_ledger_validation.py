"""Pure validation for the exact amounts written to migration-011 NUMERICs."""
from decimal import Decimal, DecimalException, ROUND_HALF_UP


CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("9999999999999999.99")  # NUMERIC(18, 2)


def _amount(value) -> Decimal:
    try:
        if isinstance(value, bool):
            raise ValueError
        raw = Decimal(str(0 if value is None else value))
        if not raw.is_finite() or raw < 0 or raw > MAX_AMOUNT:
            raise ValueError
        return raw
    except (ValueError, TypeError, DecimalException) as exc:
        raise ValueError("LEDGER_LINES_INVALID: invalid monetary amount") from exc


def prepare_posted_ledger_lines(raw_lines) -> tuple[list[dict], Decimal, Decimal]:
    """Validate every line and balance the rounded amounts that will be stored.

    Preserve caller data; do not skip invalid accounts, coerce invalid numbers
    to zero, guess a balancing line, or change the journal to repair rounding.
    """
    if not isinstance(raw_lines, list) or not raw_lines:
        raise ValueError("LEDGER_LINES_INVALID: journal lines required")
    lines = []
    for line in raw_lines:
        if not isinstance(line, dict):
            raise ValueError("LEDGER_LINES_INVALID: journal line must be an object")
        code = str(line.get("account_code") or "").strip()
        if not code:
            raise ValueError("LEDGER_LINES_INVALID: account code required")
        debit = _amount(line.get("debit", 0))
        credit = _amount(line.get("credit", 0))
        if debit > 0 and credit > 0:
            raise ValueError("LEDGER_LINES_INVALID: both monetary sides are positive")
        debit = debit.quantize(CENT, rounding=ROUND_HALF_UP)
        credit = credit.quantize(CENT, rounding=ROUND_HALF_UP)
        if (debit > 0) == (credit > 0):
            raise ValueError("LEDGER_LINES_INVALID: exactly one positive side required")
        lines.append({**line, "account_code": code, "debit": debit, "credit": credit})
    total_debit = sum((line["debit"] for line in lines), Decimal("0.00"))
    total_credit = sum((line["credit"] for line in lines), Decimal("0.00"))
    if total_debit != total_credit:
        raise ValueError("LEDGER_UNBALANCED: stored debits and credits must agree")
    if total_debit > MAX_AMOUNT:
        raise ValueError("LEDGER_LINES_INVALID: journal total exceeds numeric range")
    return lines, total_debit, total_credit
