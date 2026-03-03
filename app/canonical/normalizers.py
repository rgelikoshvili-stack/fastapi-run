COUNTERPARTY_ALIASES = {
    "tbc":              "TBC Bank",
    "tbc bank":         "TBC Bank",
    "bog":              "Bank of Georgia",
    "bank of georgia":  "Bank of Georgia",
    "rs.ge":            "Revenue Service",
    "revenue service":  "Revenue Service",
    "sarevizoro":       "Revenue Service",
    "telasi":           "Telasi",
    "gwp":              "GWP Insurance",
    "magti":            "Magti",
    "geocell":          "Geocell",
    "silknet":          "Silknet",
    "cartu":            "Cartu Bank",
    "liberty":          "Liberty Bank",
    "paybox":           "PayBox",
    "payze":            "Payze",
    "bog pay":          "Bank of Georgia",
}

def normalize_counterparty(raw: str) -> str:
    if not raw:
        return raw
    cleaned = raw.strip().lower()
    for alias, normalized in COUNTERPARTY_ALIASES.items():
        if alias in cleaned:
            return normalized
    words = cleaned.split()
    return " ".join(w.capitalize() for w in words)
