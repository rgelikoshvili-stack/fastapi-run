"""
app/compliance/masking.py
Bridge Hub — PII და Financial Data Masking
"""
import re


# ========== Masking Rules ==========

def mask_card_number(text: str) -> str:
    """
    საბანკო ბარათის ნომრის დამალვა.
    მაგ: 4111 1111 1111 1111 → **** **** **** 1111
    """
    pattern = r'\b(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})[\s-]?(\d{4})\b'
    return re.sub(pattern, r'**** **** **** \4', text)


def mask_iban(text: str) -> str:
    """
    IBAN-ის დამალვა.
    მაგ: GE29NB0000000101904917 → GE29****4917
    """
    pattern = r'\b([A-Z]{2}\d{2})[A-Z0-9]{10,}([A-Z0-9]{4})\b'
    return re.sub(pattern, r'\1****\2', text)


def mask_personal_id(text: str) -> str:
    """
    პირადი ნომრის დამალვა (11 ციფრი).
    მაგ: 01234567890 → 012****890
    """
    pattern = r'\b(\d{3})\d{5}(\d{3})\b'
    return re.sub(pattern, r'\1*****\2', text)


def mask_phone(text: str) -> str:
    """
    ტელეფონის ნომრის დამალვა.
    მაგ: +995 599 123456 → +995 ***456
    """
    pattern = r'(\+?995|0)?[\s-]?(\d{3})[\s-]?(\d{3})[\s-]?(\d{3})'
    return re.sub(pattern, r'\1 ***\4', text)


def mask_email(text: str) -> str:
    """
    Email-ის დამალვა.
    მაგ: john@example.com → j***@example.com
    """
    pattern = r'\b([a-zA-Z0-9])[a-zA-Z0-9._%+-]*@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'
    return re.sub(pattern, r'\1***@\2', text)


# ========== Full Masking ==========

def mask_pii(text: str) -> str:
    """
    ყველა PII-ს დამალვა ერთ ფუნქციაში.
    """
    if not text:
        return text
    text = mask_card_number(text)
    text = mask_iban(text)
    text = mask_personal_id(text)
    text = mask_phone(text)
    text = mask_email(text)
    return text


def mask_dict(data: dict, fields_to_mask: list = None) -> dict:
    """
    Dictionary-ში სენსიტიური ველების დამალვა.
    """
    if fields_to_mask is None:
        fields_to_mask = [
            "api_key", "password", "secret", "token",
            "card_number", "iban", "personal_id",
        ]

    result = {}
    for key, value in data.items():
        if key.lower() in [f.lower() for f in fields_to_mask]:
            if isinstance(value, str) and len(value) > 4:
                result[key] = value[:2] + "*" * (len(value) - 4) + value[-2:]
            else:
                result[key] = "****"
        elif isinstance(value, str):
            result[key] = mask_pii(value)
        elif isinstance(value, dict):
            result[key] = mask_dict(value, fields_to_mask)
        else:
            result[key] = value
    return result


def mask_amount(amount: float, show_last_digits: int = 2) -> str:
    """
    თანხის ნაწილობრივი დამალვა debug-ისთვის.
    მაგ: 12345.67 → ***45.67
    """
    amount_str = f"{amount:.2f}"
    if len(amount_str) <= show_last_digits + 3:
        return amount_str
    return "***" + amount_str[-(show_last_digits + 3):]