import re
from typing import Optional

def normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""

    text = value.strip().lower()
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = text.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    text = re.sub(r"\s+", " ", text)

    # remove punctuation except letters/numbers/spaces
    text = re.sub(r"[^\w\s\u10A0-\u10FF]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text).strip()

    return text