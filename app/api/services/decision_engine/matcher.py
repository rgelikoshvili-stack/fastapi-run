"""
decision_engine/matcher.py
Hybrid Matcher: Exact → Partial (GPT-4o breakdown + greedy WRatio).
"""
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from .normalize import normalize_text, normalize_partner, partner_similarity

log = logging.getLogger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────────────
EXACT_AMOUNT_DIFF_PCT = Decimal("0.01")   # 1 %
EXACT_AMOUNT_DIFF_ABS = Decimal("1.00")   # 1 GEL
EXACT_PARTNER_SIM = 90
EXACT_DATE_DIFF_DAYS = 3

PARTIAL_TEXT_SIM = 85
PARTIAL_AMOUNT_TOL_PCT = Decimal("0.05")  # 5 %

RESIDUAL_MIN_GEL = Decimal("5.00")


def _to_date(v) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(str(v), fmt).date()
        except ValueError:
            pass
    return None


def _amount_score(a: Decimal, b: Decimal) -> float:
    if b == 0:
        return 1.0 if a == 0 else 0.0
    diff_abs = abs(a - b)
    diff_pct = diff_abs / b
    if diff_abs <= EXACT_AMOUNT_DIFF_ABS or diff_pct <= EXACT_AMOUNT_DIFF_PCT:
        return 1.0
    if diff_pct <= Decimal("0.05"):
        return float(1.0 - diff_pct / Decimal("0.05")) * 0.8
    return 0.0


def _text_score(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    try:
        from rapidfuzz import fuzz
        return fuzz.WRatio(a, b) / 100.0
    except ImportError:
        return 1.0 if a == b else 0.0


def _date_score(d1, d2) -> float:
    a, b = _to_date(d1), _to_date(d2)
    if a is None or b is None:
        return 0.5
    diff = abs((a - b).days)
    if diff <= EXACT_DATE_DIFF_DAYS:
        return 1.0
    if diff <= 7:
        return 0.6
    return max(0.0, 1.0 - diff / 30)


def calculate_confidence(amount: float, text: float, partner: float, date_s: float) -> float:
    return min(1.0, round(
        0.4 * amount +
        0.3 * text +
        0.2 * partner +
        0.1 * date_s,
        4,
    ))


def exact_match(invoice: dict, candidates: list[dict]) -> Optional[dict]:
    """
    Returns the best exact-match candidate or None.
    Criteria: amount ≤1%/1GEL, partner ≥90, date ≤3d.
    """
    inv_amount = Decimal(str(invoice.get("amount") or 0))
    inv_partner_raw = invoice.get("partner") or ""
    inv_date = invoice.get("date")
    inv_text = normalize_text(invoice.get("description") or "")

    best = None
    best_conf = 0.0

    for cand in candidates:
        cand_amount = Decimal(str(cand.get("amount") or 0))
        a_score = _amount_score(inv_amount, cand_amount)
        if a_score < 0.95:
            continue

        p_sim = partner_similarity(inv_partner_raw, cand.get("partner") or "")
        if p_sim < EXACT_PARTNER_SIM:
            continue

        d_score = _date_score(inv_date, cand.get("date"))
        t_score = _text_score(inv_text, normalize_text(cand.get("description") or ""))

        conf = calculate_confidence(a_score, t_score, p_sim / 100.0, d_score)
        if conf > best_conf:
            best_conf = conf
            best = {
                "match_type": "exact",
                "matched_candidate": cand,
                "confidence": conf,
                "scores": {
                    "amount": a_score,
                    "text": t_score,
                    "partner": p_sim / 100.0,
                    "date": d_score,
                },
                "autopilot_flag": "ready_for_approval",
            }

    return best if best_conf >= 0.95 else None


def gpt4o_breakdown(description: str, total_amount: float, tenant_id: str) -> list[dict]:
    """
    Ask GPT-4o to break an invoice description into line items.
    Returns list of {description, amount} or empty list on failure.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log.warning("gpt4o_breakdown: no API key — skipping AI breakdown")
        return []

    prompt = (
        f"Invoice description: {description}\n"
        f"Total amount: {total_amount} GEL\n\n"
        "Split this invoice into individual line items. "
        "Return ONLY a JSON array, no extra text:\n"
        '[{"description": "...", "amount": 0.00}, ...]'
    )

    for attempt in range(2):
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1" if os.environ.get("OPENROUTER_API_KEY") else None,
            )
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are an accounting assistant. Return only valid JSON arrays."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=600,
            )
            raw = resp.choices[0].message.content.strip()

            parsed = json.loads(raw)
            lines = parsed if isinstance(parsed, list) else parsed.get("lines") or parsed.get("items") or []

            if not isinstance(lines, list):
                raise ValueError("unexpected structure")

            validated = []
            for item in lines:
                desc = str(item.get("description") or "").strip()
                try:
                    amt = float(item.get("amount") or 0)
                except (TypeError, ValueError):
                    amt = 0.0
                if desc and amt > 0:
                    validated.append({"description": desc, "amount": amt})

            if validated:
                return validated

        except Exception as e:
            log.warning("gpt4o_breakdown attempt %d failed: %s", attempt + 1, e)

    return []


def partial_match(invoice: dict, candidates: list[dict], tenant_id: str = "default") -> dict:
    """
    Greedy WRatio-based partial matching.
    Returns matched lines, unmatched residual, confidence.
    """
    inv_amount = Decimal(str(invoice.get("amount") or 0))
    inv_partner_raw = invoice.get("partner") or ""
    inv_date = invoice.get("date")
    inv_text = normalize_text(invoice.get("description") or "")

    # Step 1: get line breakdown from GPT-4o
    breakdown = gpt4o_breakdown(
        invoice.get("description") or "",
        float(inv_amount),
        tenant_id,
    )
    if not breakdown:
        breakdown = [{"description": invoice.get("description") or "", "amount": float(inv_amount)}]

    matched_lines = []
    unmatched_cands = list(candidates)
    matched_sum = Decimal("0.00")

    for line in breakdown:
        line_amt = Decimal(str(line["amount"]))
        line_text = normalize_text(line["description"])
        best_score = 0.0
        best_cand = None
        best_idx = -1

        for idx, cand in enumerate(unmatched_cands):
            try:
                from rapidfuzz import fuzz
                text_sim = fuzz.WRatio(line_text, normalize_text(cand.get("description") or "")) / 100.0
            except ImportError:
                text_sim = 0.5

            cand_amt = Decimal(str(cand.get("amount") or 0))
            if cand_amt > 0:
                amt_diff_pct = abs(line_amt - cand_amt) / cand_amt
                amt_score = 1.0 - min(float(amt_diff_pct / PARTIAL_AMOUNT_TOL_PCT), 1.0)
            else:
                amt_score = 0.0

            composite = 0.6 * text_sim + 0.4 * amt_score
            if composite > best_score and text_sim * 100 >= PARTIAL_TEXT_SIM:
                best_score = composite
                best_cand = cand
                best_idx = idx

        if best_cand is not None and best_idx >= 0:
            matched_lines.append({
                "line_description": line["description"],
                "line_amount": float(line_amt),
                "matched_candidate": best_cand,
                "similarity_score": round(best_score, 4),
            })
            matched_sum += Decimal(str(best_cand.get("amount") or line_amt))
            unmatched_cands.pop(best_idx)
        else:
            matched_lines.append({
                "line_description": line["description"],
                "line_amount": float(line_amt),
                "matched_candidate": None,
                "similarity_score": 0.0,
            })

    residual = inv_amount - matched_sum
    p_sim = partner_similarity(inv_partner_raw, (candidates[0].get("partner") or "") if candidates else "")
    d_score = _date_score(inv_date, (candidates[0].get("date") or None) if candidates else None)

    conf = calculate_confidence(
        _amount_score(inv_amount, matched_sum),
        _text_score(inv_text, normalize_text((candidates[0].get("description") or "") if candidates else "")),
        p_sim / 100.0,
        d_score,
    )

    return {
        "match_type": "partial",
        "lines": matched_lines,
        "residual": float(residual),
        "residual_significant": abs(residual) >= RESIDUAL_MIN_GEL,
        "confidence": conf,
        "autopilot_flag": "ready_for_approval" if conf >= 0.85 else "needs_review",
    }
