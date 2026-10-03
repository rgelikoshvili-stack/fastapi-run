"""app/api/services/cashflow_classification_service.py
IAS 7 — Statement of Cash Flows classification engine.

Pure functions only — no DB access, fully testable without infrastructure.

Policy decisions (documented):
- Interest paid → operating activities (IAS 7.33 allowed treatment)
- Dividends paid → financing activities
- Internal transfers (1110↔1120) → excluded from cashflow totals
- Non-cash items (depreciation, FX revaluation, accruals) → excluded
- Prepaid initial payment → operating outflow (when cash leaves)
- Prepaid monthly recognition (Dr expense / Cr prepaid) → non-cash, excluded
"""
from __future__ import annotations

from typing import Any

# ── Cash / bank account codes ─────────────────────────────────────────────────
CASH_ACCOUNTS = frozenset({"1110", "1120"})

# ── Non-cash account codes (never produce a cashflow movement) ────────────────
NON_CASH_ACCOUNTS = frozenset({
    "7610",   # depreciation expense
    "1520",   # accumulated depreciation (contra asset)
    "7920",   # FX revaluation loss (unrealised)
    "6150",   # unrealised FX gain
})

# ── Internal transfer pair (excluded from cashflow totals) ───────────────────
INTERNAL_TRANSFER_PAIRS = frozenset({
    frozenset({"1110", "1120"}),  # bank ↔ cash
})

# ── Classification: when cash/bank is DEBITED (money FLOWS IN) ───────────────
# Key = counterpart account code (credit side); Value = cashflow category
INFLOW_CLASSIFICATION: dict[str, str] = {
    # Operating inflows
    "1210": "operating",   # customer receipt (AR cleared)
    "1220": "operating",   # doubtful debts recovered
    "3120": "operating",   # customer advance received
    "6110": "operating",   # direct revenue receipt (rare)
    "6120": "operating",   # service revenue receipt
    "6130": "operating",   # other operating income receipt
    # Financing inflows
    "3410": "financing",   # short-term loan received
    "3510": "financing",   # long-term loan received
    "4110": "financing",   # equity / share capital contribution
    "4120": "financing",   # additional paid-in capital
    # Internal transfers — excluded
    "1110": "internal",    # cash transferred to bank
    "1120": "internal",    # bank transferred to cash
}

# ── Classification: when cash/bank is CREDITED (money FLOWS OUT) ─────────────
# Key = counterpart account code (debit side); Value = cashflow category
OUTFLOW_CLASSIFICATION: dict[str, str] = {
    # Operating outflows
    "3110": "operating",   # supplier payment (AP cleared)
    "7310": "operating",   # rent (paid directly without AP accrual)
    "3130": "operating",   # accrued expenses paid (salary payable, etc.)
    "3360": "operating",   # net salary payment
    "3320": "operating",   # PIT payment to tax authority
    "3330": "operating",   # employee PAYG (pension)
    "3335": "operating",   # employer PAYG (pension)
    "3340": "operating",   # CIT payment
    "3350": "operating",   # withholding tax payment
    "3380": "operating",   # other taxes paid
    "1420": "operating",   # supplier advance paid (prepayment to supplier)
    "1430": "operating",   # prepaid expense payment (insurance, etc.)
    "3420": "operating",   # interest payment (operating per IAS 7.33 policy)
    "7520": "operating",   # interest paid (direct, no accrual)
    "7310_direct": "operating",  # rent paid directly
    # Investing outflows
    "1510": "investing",   # fixed asset purchase
    "1610": "investing",   # intangible asset purchase
    "1620": "investing",   # long-term investment purchase
    "1710": "investing",   # right-of-use asset (IFRS 16 lease)
    # Financing outflows
    "3370": "financing",   # dividend payment
    "3410": "financing",   # loan principal repayment
    "3510": "financing",   # long-term loan repayment
    # Internal transfers — excluded
    "1110": "internal",    # bank transferred to cash
    "1120": "internal",    # cash transferred to bank
}

_VALID_CATEGORIES = frozenset({"operating", "investing", "financing", "internal", "non_cash"})
_CASH_MOVEMENT_CATEGORIES = frozenset({"operating", "investing", "financing", "internal"})
_EXPECTED_ACCOUNT_TYPES: dict[str, frozenset[str]] = {
    **{
        code: frozenset({"asset"})
        for code in ("1210", "1220", "1420", "1430", "1510", "1610", "1620", "1710")
    },
    **{
        code: frozenset({"liability"})
        for code in ("3120", "3110", "3130", "3360", "3320", "3330", "3335", "3340", "3350", "3380", "3420", "3410", "3510")
    },
    **{code: frozenset({"income"}) for code in ("6110", "6120", "6130")},
    **{code: frozenset({"expense"}) for code in ("7310", "7520")},
    **{code: frozenset({"equity"}) for code in ("4110", "4120")},
    "3370": frozenset({"equity", "liability"}),
}


def classify_cashflow_line(
    dr: str,
    cr: str,
    amount: float,
    *,
    cashflow_category: str | None = None,
    counterpart_account_type: str | None = None,
) -> dict[str, Any]:
    """Classify a single journal line pair into cashflow categories.

    Returns:
        {
          "category": "operating" | "investing" | "financing" | "internal" | "non_cash" | "unknown",
          "direction": "inflow" | "outflow" | "none",
          "amount": float,
          "dr": str,
          "cr": str,
          "note": str,
        }
    """
    dr = (dr or "").strip()
    cr = (cr or "").strip()
    amt = round(abs(float(amount or 0)), 2)

    # Non-cash accounts involved → exclude
    if dr in NON_CASH_ACCOUNTS or cr in NON_CASH_ACCOUNTS:
        return _result("non_cash", "none", amt, dr, cr, "non-cash item excluded")

    # Internal transfer check (both sides are cash accounts)
    if dr in CASH_ACCOUNTS and cr in CASH_ACCOUNTS:
        return _result("internal", "none", amt, dr, cr, "internal cash-bank transfer excluded")

    # Cash/bank DEBIT (inflow): DR=cash, CR=counterpart
    if dr in CASH_ACCOUNTS:
        category = _resolve_category(
            cr, INFLOW_CLASSIFICATION, cashflow_category, counterpart_account_type
        )
        if category == "internal":
            return _result("internal", "none", amt, dr, cr, "internal transfer excluded")
        return _result(category, "inflow", amt, dr, cr, f"cash inflow via {cr}")

    # Cash/bank CREDIT (outflow): CR=cash, DR=counterpart
    if cr in CASH_ACCOUNTS:
        category = _resolve_category(
            dr, OUTFLOW_CLASSIFICATION, cashflow_category, counterpart_account_type
        )
        if category == "internal":
            return _result("internal", "none", amt, dr, cr, "internal transfer excluded")
        return _result(category, "outflow", amt, dr, cr, f"cash outflow via {dr}")

    # Neither side is cash → non-cash journal entry
    return _result("non_cash", "none", amt, dr, cr, "no cash account involved")


def _resolve_category(
    counterpart_code: str,
    fallback_map: dict[str, str],
    cashflow_category: str | None,
    account_type: str | None,
) -> str:
    """Prefer explicit ledger classification; use the COA map only as a guarded legacy fallback."""
    explicit = (cashflow_category or "").strip().lower()
    if explicit:
        return explicit if explicit in _VALID_CATEGORIES else "unknown"

    category = fallback_map.get(counterpart_code, "unknown")
    expected_types = _EXPECTED_ACCOUNT_TYPES.get(counterpart_code)
    actual_type = (account_type or "").strip().lower()
    if (
        category != "unknown"
        and actual_type
        and expected_types
        and actual_type not in expected_types
    ):
        return "unknown"
    return category


def build_cashflow_from_posted_ledger_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build cashflow from posted ledger rows, anchoring one movement per cash line.

    A cash line's explicit ``cashflow_category`` wins. Without one, classification
    is inferred only if its non-cash counterpart(s) agree; ambiguous compound
    entries are reported as unknown rather than multiplied or guessed.
    """
    from collections import defaultdict

    by_header: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_header[row.get("header_id")].append(row)

    movements: list[dict[str, Any]] = []
    for header_lines in by_header.values():
        cash_lines = [
            line for line in header_lines
            if str(line.get("account_code") or "").strip() in CASH_ACCOUNTS
        ]
        cash_debits = sum(float(line.get("debit") or 0) for line in cash_lines)
        cash_credits = sum(float(line.get("credit") or 0) for line in cash_lines)
        if cash_debits > 0 and cash_credits > 0:
            non_cash_lines = [
                line for line in header_lines
                if all(line is not cash_line for cash_line in cash_lines)
            ]
            if not non_cash_lines and abs(cash_debits - cash_credits) < 0.005:
                movements.append({
                    "dr": "1110", "cr": "1120", "amount": cash_debits,
                    "cashflow_category": "internal", "description": "internal cash transfer",
                })
            else:
                # Mixed cash-in/cash-out compound entries need explicit per-line
                # cashflow categories; otherwise do not guess or duplicate them.
                for line in cash_lines:
                    movements.append({
                        "dr": str(line.get("account_code") or ""), "cr": "",
                        "amount": float(line.get("debit") or line.get("credit") or 0),
                        "cashflow_category": "invalid",
                        "description": line.get("description") or "",
                    })
            continue

        for cash in header_lines:
            cash_code = str(cash.get("account_code") or "").strip()
            if cash_code not in CASH_ACCOUNTS:
                continue
            cash_type = (cash.get("account_type") or "").strip().lower()
            if cash_type and cash_type not in {"asset", "cash", "bank"}:
                movements.append({
                    "dr": cash_code,
                    "cr": "",
                    "amount": float(cash.get("debit") or cash.get("credit") or 0),
                    "cashflow_category": "invalid",
                    "description": cash.get("description") or "",
                })
                continue

            debit = float(cash.get("debit") or 0)
            credit = float(cash.get("credit") or 0)
            if debit > 0 and credit > 0:
                movements.append({
                    "dr": cash_code,
                    "cr": cash_code,
                    "amount": debit + credit,
                    "description": cash.get("description") or "",
                })
                continue
            if debit <= 0 and credit <= 0:
                continue

            is_inflow = debit > 0
            amount = debit if is_inflow else credit
            counterparty_rows = [
                line for line in header_lines
                if line is not cash
                and (float(line.get("credit") or 0) if is_inflow else float(line.get("debit") or 0)) > 0
                and str(line.get("account_code") or "").strip() not in CASH_ACCOUNTS
            ]
            explicit = (cash.get("cashflow_category") or "").strip().lower()
            if explicit:
                counterparty = counterparty_rows[0] if len(counterparty_rows) == 1 else {}
                counterpart_code = (
                    str(counterparty.get("account_code") or "")
                    if counterparty else ("MULTIPLE" if counterparty_rows else "")
                )
                dr, cr = (cash_code, counterpart_code) if is_inflow else (counterpart_code, cash_code)
                safe_category = explicit if explicit in _CASH_MOVEMENT_CATEGORIES else "invalid"
                movements.append({
                    "dr": dr,
                    "cr": cr,
                    "amount": amount,
                    "cashflow_category": safe_category,
                    "counterpart_account_type": counterparty.get("account_type"),
                    "description": cash.get("description") or "",
                })
                continue

            candidates: list[tuple[dict[str, Any], str]] = []
            for counterparty in counterparty_rows:
                code = str(counterparty.get("account_code") or "").strip()
                dr, cr = (cash_code, code) if is_inflow else (code, cash_code)
                category = classify_cashflow_line(
                    dr, cr, amount,
                    cashflow_category=counterparty.get("cashflow_category"),
                    counterpart_account_type=counterparty.get("account_type"),
                )["category"]
                if category not in _CASH_MOVEMENT_CATEGORIES:
                    category = "unknown"
                candidates.append((counterparty, category))

            categories = {category for _, category in candidates}
            category = next(iter(categories)) if len(categories) == 1 else "unknown"
            counterparty = candidates[0][0] if candidates else {}
            code = (
                str(counterparty.get("account_code") or "").strip()
                if len(candidates) == 1 else ("MULTIPLE" if candidates else "")
            )
            dr, cr = (cash_code, code) if is_inflow else (code, cash_code)
            movements.append({
                "dr": dr, "cr": cr, "amount": amount,
                "cashflow_category": category,
                "counterpart_account_type": counterparty.get("account_type"),
                "description": cash.get("description") or "",
            })

    return build_cashflow_direct(movements)


def _result(
    category: str,
    direction: str,
    amount: float,
    dr: str,
    cr: str,
    note: str,
) -> dict[str, Any]:
    return {
        "category": category,
        "direction": direction,
        "amount": amount,
        "dr": dr,
        "cr": cr,
        "note": note,
    }


def build_cashflow_direct(
    lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Classify a list of journal line pairs and aggregate into cashflow sections.

    Each line: {"dr": str, "cr": str, "amount": float, "description": str (optional)}

    Returns:
        {
          "operating": {"inflows": float, "outflows": float, "net": float, "lines": [...]},
          "investing": {"inflows": float, "outflows": float, "net": float, "lines": [...]},
          "financing": {"inflows": float, "outflows": float, "net": float, "lines": [...]},
          "internal_transfers": {"amount": float, "lines": [...]},
          "non_cash": {"lines": [...]},
          "unknown": {"lines": [...]},
          "net_change_in_cash": float,
          "policy_notes": [...],
        }
    """
    sections: dict[str, Any] = {
        "operating": {"inflows": 0.0, "outflows": 0.0, "net": 0.0, "lines": []},
        "investing": {"inflows": 0.0, "outflows": 0.0, "net": 0.0, "lines": []},
        "financing": {"inflows": 0.0, "outflows": 0.0, "net": 0.0, "lines": []},
        "internal_transfers": {"amount": 0.0, "lines": []},
        "non_cash": {"lines": []},
        "unknown": {"lines": []},
    }

    for raw in lines:
        classified = classify_cashflow_line(
            raw.get("dr", ""),
            raw.get("cr", ""),
            raw.get("amount", 0.0),
            cashflow_category=raw.get("cashflow_category"),
            counterpart_account_type=raw.get("counterpart_account_type"),
        )
        classified["description"] = raw.get("description", "")
        cat = classified["category"]
        direction = classified["direction"]
        amt = classified["amount"]

        if cat in ("operating", "investing", "financing"):
            sec = sections[cat]
            sec["lines"].append(classified)
            if direction == "inflow":
                sec["inflows"] = round(sec["inflows"] + amt, 2)
            elif direction == "outflow":
                sec["outflows"] = round(sec["outflows"] + amt, 2)
        elif cat == "internal":
            sections["internal_transfers"]["lines"].append(classified)
            sections["internal_transfers"]["amount"] = round(
                sections["internal_transfers"]["amount"] + amt, 2
            )
        elif cat == "non_cash":
            sections["non_cash"]["lines"].append(classified)
        else:
            sections["unknown"]["lines"].append(classified)

    for cat in ("operating", "investing", "financing"):
        sec = sections[cat]
        sec["net"] = round(sec["inflows"] - sec["outflows"], 2)

    net_change = round(
        sections["operating"]["net"]
        + sections["investing"]["net"]
        + sections["financing"]["net"],
        2,
    )

    return {
        **sections,
        "net_change_in_cash": net_change,
        "policy_notes": [
            "Interest paid classified as operating (IAS 7.33)",
            "Internal bank↔cash transfers excluded from totals",
            "Depreciation and FX revaluation excluded (non-cash)",
            "Prepaid payment = operating outflow when cash leaves",
            "Prepaid monthly recognition = non-cash, excluded",
        ],
    }


def build_cashflow_indirect(
    net_profit_loss: float,
    depreciation: float = 0.0,
    fx_revaluation_loss: float = 0.0,
    working_capital_changes: dict[str, float] | None = None,
    investing_net: float = 0.0,
    financing_net: float = 0.0,
) -> dict[str, Any]:
    """Build indirect-method cashflow statement.

    Operating cashflow = net profit + non-cash adjustments + working capital changes.

    Args:
        net_profit_loss: Net profit (positive) or loss (negative)
        depreciation: Depreciation charge (positive = add-back)
        fx_revaluation_loss: Unrealised FX loss (positive = add-back)
        working_capital_changes: dict of {label: amount} where positive = source of cash
        investing_net: Net investing cashflow (typically negative)
        financing_net: Net financing cashflow

    Returns:
        Indirect cashflow statement dict
    """
    wc = working_capital_changes or {}
    total_wc = round(sum(wc.values()), 2)
    total_non_cash = round(depreciation + fx_revaluation_loss, 2)
    operating_net = round(net_profit_loss + total_non_cash + total_wc, 2)
    net_change = round(operating_net + investing_net + financing_net, 2)

    return {
        "method": "indirect",
        "operating_activities": {
            "net_profit_loss": round(net_profit_loss, 2),
            "adjustments_for_non_cash": {
                "depreciation": round(depreciation, 2),
                "fx_revaluation_loss": round(fx_revaluation_loss, 2),
                "total": round(total_non_cash, 2),
            },
            "working_capital_changes": {**wc, "total": total_wc},
            "net": operating_net,
        },
        "investing_activities": {
            "net": round(investing_net, 2),
        },
        "financing_activities": {
            "net": round(financing_net, 2),
        },
        "net_change_in_cash": net_change,
        "policy_notes": [
            "Interest paid classified as operating (IAS 7.33)",
            "Depreciation added back as non-cash item",
            "Unrealised FX revaluation added back as non-cash",
        ],
    }
