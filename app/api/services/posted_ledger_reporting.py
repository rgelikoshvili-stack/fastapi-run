"""Shared functional-GEL SQL basis for posted-ledger readers.

No FX lookup, guessed rate, schema mutation or historical repair occurs here.
Old GEL rows with the schema's zero amount_gel default keep their exact raw
GEL amounts; foreign rows require valid, consistent stored posting evidence.
"""
from decimal import Decimal, ROUND_HALF_EVEN, localcontext

from app.knowledge.chart_of_accounts import CHART_OF_ACCOUNTS


def report_money_sum(values, *, rounded=True):
    """Keep booked NUMERIC cents through arithmetic, before JSON conversion.

    Fifty digits cover NUMERIC(18,2) ledger values and aggregate headroom.
    Use a local context so unrelated callers cannot lower report precision.
    This does not change posting/FX rounding or manufacture missing balances.
    """
    with localcontext() as context:
        context.prec = 50
        total = sum((Decimal(str(value or 0)) for value in values), Decimal(0))
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN) if rounded else total


def report_money_net(debit, credit, *, rounded=True):
    return report_money_sum((debit, Decimal(str(credit or 0)).copy_negate()), rounded=rounded)


def report_json_numbers(value):
    """Preserve existing numeric API fields only at the final response boundary.

    Arbitrarily large final floats still cannot encode every cent. A versioned
    exact-decimal transport contract remains separate from correct arithmetic.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: report_json_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [report_json_numbers(item) for item in value]
    return value

POSTED_CLASS_ERROR = "LEDGER_CLASSIFICATION_INCOMPLETE"
_CANONICAL_TYPES = {"asset", "liability", "equity", "income", "expense"}


class UnclassifiedLedgerAccount(ValueError):
    pass


def canonical_account_type(code):
    kind = CHART_OF_ACCOUNTS.get(str(code).strip(), {}).get("type")
    kind = {"revenue": "income", "contra_asset": "asset"}.get(kind, kind)
    return kind if kind in _CANONICAL_TYPES else None


def classify_ledger_lines(lines):
    result = []
    for line in lines:
        kind = canonical_account_type(line.get("account_code", ""))
        if kind is None:
            raise UnclassifiedLedgerAccount("LEDGER_ACCOUNT_UNCLASSIFIED: canonical account mapping required")
        result.append(dict(line, account_type=kind))
    return result


def basis_error_code(error):
    return POSTED_CLASS_ERROR if str(error) == POSTED_CLASS_ERROR else POSTED_FX_ERROR


POSTED_FX_ERROR = "POSTED_LEDGER_FX_INVALID"


def functional_ledger_cte(date_filter: str = "") -> str:
    """Internal SQL only; date_filter contains generated placeholders, not input."""
    # The registry is repository-owned data, never a caller-supplied SQL value.
    cases = " ".join(
        "WHEN '" + code.replace("'", "''") + "' THEN '" + canonical_account_type(code) + "'"
        for code in sorted(CHART_OF_ACCOUNTS) if canonical_account_type(code)
    )
    expected = "CASE jel.account_code " + cases + " ELSE NULL END"
    normalized = "NULLIF(CASE lower(btrim(jel.account_type)) WHEN 'revenue' THEN 'income' WHEN 'contra_asset' THEN 'asset' ELSE lower(btrim(jel.account_type)) END, '')"
    account_type = f"COALESCE({normalized}, {expected})"
    classification_valid = f"{account_type} IN ('asset','liability','equity','income','expense') AND ({expected} IS NULL OR {account_type} = {expected})"
    debit = "CASE WHEN jel.currency = 'GEL' THEN jel.debit WHEN jel.debit > 0 THEN jel.amount_gel ELSE 0 END"
    credit = "CASE WHEN jel.currency = 'GEL' THEN jel.credit WHEN jel.credit > 0 THEN jel.amount_gel ELSE 0 END"
    valid = """
        jel.currency = jeh.currency
        AND jel.currency ~ '^[A-Z]{3}$'
        AND jel.exchange_rate = jeh.exchange_rate
        AND jel.exchange_rate > 0 AND jel.exchange_rate <= 9999999999.99999999
        AND jel.debit >= 0 AND jel.debit <= 9999999999999999.99
        AND jel.credit >= 0 AND jel.credit <= 9999999999999999.99
        AND ((jel.debit > 0 AND jel.credit = 0) OR (jel.credit > 0 AND jel.debit = 0))
        AND jel.amount_gel >= 0 AND jel.amount_gel <= 9999999999999999.99
        AND (
            (jel.currency = 'GEL' AND jel.exchange_rate = 1
             AND jel.amount_gel IN (0, jel.debit + jel.credit))
            OR
            (jel.currency <> 'GEL'
             AND jel.amount_gel = ROUND((jel.debit + jel.credit) * jel.exchange_rate, 2))
        )
    """
    return f"""WITH functional_ledger_lines AS (
        SELECT jel.*,
               {account_type} AS report_account_type,
               MAX(CASE WHEN {classification_valid} THEN 0 ELSE 1 END) OVER () AS classification_invalid_count,
               {debit} AS gel_debit,
               {credit} AS gel_credit,
               MAX(CASE WHEN {valid} THEN 0 ELSE 1 END) OVER journal_scope AS fx_invalid_count,
               SUM({debit}) OVER journal_scope AS gel_header_debit,
               SUM({credit}) OVER journal_scope AS gel_header_credit
        FROM journal_entry_lines jel
        JOIN journal_entry_headers jeh ON jeh.id = jel.journal_entry_id
                                     AND jel.tenant_id = jeh.tenant_id
        WHERE jeh.tenant_id = $1 AND jeh.status = ANY($2) {date_filter}
        WINDOW journal_scope AS (PARTITION BY jel.journal_entry_id)
    )
    """


# Evaluated before classification filters, on every line of the scoped journal.
FX_INVALID_LINE = "CASE WHEN jel.fx_invalid_count > 0 OR jel.gel_header_debit <> jel.gel_header_credit THEN 1 ELSE 0 END"


def assert_functional_basis(rows) -> None:
    if any(int(row.get("fx_invalid_count") or 0) for row in rows):
        raise ValueError(POSTED_FX_ERROR)
    if any(int(row.get("classification_invalid_count") or 0) for row in rows):
        raise ValueError(POSTED_CLASS_ERROR)


# Legacy drafts retain raw values, but do not retain sufficient verified posting
# FX to reconstruct historical GEL. Refuse non-GEL aggregates instead of mixing
# currencies or consulting today's rate. Missing old currency uses schema GEL.
LEGACY_FX_ERROR = "LEGACY_FX_UNAVAILABLE"
LEGACY_FX_INVALID_LINE = """CASE WHEN
    COALESCE(to_jsonb(jd)->>'currency','GEL') = 'GEL'
    AND COALESCE(entry->>'currency','GEL') = 'GEL'
    THEN 0 ELSE 1 END"""
LEGACY_FX_INVALID_HEADER = """CASE WHEN
    COALESCE(to_jsonb(jd)->>'currency','GEL') = 'GEL'
    AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(COALESCE(jd.journal_entries,'[]'::jsonb)) AS fx_entry
        WHERE COALESCE(fx_entry->>'currency','GEL') <> 'GEL'
    ) THEN 0 ELSE 1 END"""


def legacy_fx_unavailable(rows) -> bool:
    return any(int(row.get("fx_invalid_count") or 0) for row in rows)
