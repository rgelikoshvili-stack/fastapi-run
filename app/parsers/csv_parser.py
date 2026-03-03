import pandas as pd
import hashlib
from decimal import Decimal
from datetime import date as date_type
from app.schemas.canonical import CanonicalBankTransaction
from app.canonical.aliases import COLUMN_ALIASES

def resolve_columns(df: pd.DataFrame) -> dict:
    resolved = {}
    for canonical_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                resolved[canonical_name] = alias
                break
    return resolved

def clean_amount(raw) -> Decimal:
    s = str(raw).strip().replace(',', '').replace(' ', '')
    s = s.replace('(', '-').replace(')', '').strip('"').strip("'")
    try:
        return abs(Decimal(s))
    except:
        return Decimal('0')

def detect_direction(row, col_map: dict) -> str:
    if 'direction' in col_map:
        val = str(row[col_map['direction']]).upper()
        return 'OUT' if val in ['D','DR','DEBIT','OUT','-'] else 'IN'
    if 'amount' in col_map:
        raw = str(row[col_map['amount']]).strip()
        return 'OUT' if raw.startswith('-') or raw.startswith('(') else 'IN'
    return 'IN'

def parse_csv_bank_statement(filepath: str) -> list:
    df = pd.read_csv(filepath, encoding='utf-8', on_bad_lines='skip')
    col_map = resolve_columns(df)
    required = ['date', 'description', 'amount']
    missing = [f for f in required if f not in col_map]
    if missing:
        raise ValueError(f'Required columns not found: {missing}. Found: {list(df.columns)}')
    results = []
    for _, row in df.iterrows():
        amount = clean_amount(row[col_map['amount']])
        if amount == 0:
            continue
        direction = detect_direction(row, col_map)
        desc = str(row[col_map['description']]).strip()
        raw = str(row.to_dict())
        dedup_hash = hashlib.sha256(
            f"{row[col_map['date']]}|{amount}|{desc}".encode()
        ).hexdigest()
        tx = CanonicalBankTransaction(
            date=pd.to_datetime(row[col_map['date']]).date(),
            description=desc,
            amount=amount,
            currency=str(row[col_map['currency']]).strip() if 'currency' in col_map else 'GEL',
            direction=direction,
            counterparty=str(row[col_map['counterparty']]).strip() if 'counterparty' in col_map else None,
            raw_reference=raw,
            source_file_type='csv',
            duplicate_hash=dedup_hash,
            confidence=0.95,
        )
        results.append(tx)
    return results
