import pandas as pd
from app.schemas.canonical import CanonicalBankTransaction
from app.parsers.csv_parser import resolve_columns, clean_amount, detect_direction
import hashlib

def parse_xlsx_statement(filepath: str) -> list:
    df = pd.read_excel(filepath, engine='openpyxl')
    col_map = resolve_columns(df)
    required = ['date', 'description', 'amount']
    missing = [f for f in required if f not in col_map]
    if missing:
        raise ValueError(f'Required columns not found: {missing}')
    results = []
    for _, row in df.iterrows():
        amount = clean_amount(row[col_map['amount']])
        if amount == 0:
            continue
        direction = detect_direction(row, col_map)
        desc = str(row[col_map['description']]).strip()
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
            source_file_type='xlsx',
            duplicate_hash=dedup_hash,
            confidence=0.95,
        )
        results.append(tx)
    return results
