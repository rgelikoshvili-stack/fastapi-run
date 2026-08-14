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


def classify_cashflow_line(
    dr: str,
    cr: str,
    amount: float,
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
        category = INFLOW_CLASSIFICATION.get(cr, "unknown")
        if category == "internal":
            return _result("internal", "none", amt, dr, cr, "internal transfer excluded")
        return _result(category, "inflow", amt, dr, cr, f"cash inflow via {cr}")

    # Cash/bank CREDIT (outflow): CR=cash, DR=counterpart
    if cr in CASH_ACCOUNTS:
        category = OUTFLOW_CLASSIFICATION.get(dr, "unknown")
        if category == "internal":
            return _result("internal", "none", amt, dr, cr, "internal transfer excluded")
        return _result(category, "outflow", amt, dr, cr, f"cash outflow via {dr}")

    # Neither side is cash → non-cash journal entry
    return _result("non_cash", "none", amt, dr, cr, "no cash account involved")


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
