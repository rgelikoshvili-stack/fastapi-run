# Georgian Tax Code — Key Constants (Codex R4, 2014)
# Source: საქართველოს საგადასახადო კოდექსი

GEORGIAN_TAX_CONSTANTS = {
    "vat_standard_rate":        0.18,   # მუხლი 166 — 18%
    "vat_registration_threshold": 100000, # 100,000 GEL
    "vat_zero_rate":            0.0,    # ექსპორტი
    "income_tax_rate":          0.20,   # საშემოსავლო გადასახადი 20%
    "profit_tax_rate":          0.15,   # მოგების გადასახადი 15%
    "micro_business_threshold": 30000,  # მიკრო ბიზნესი — 30,000 GEL
    "small_business_threshold": 500000, # მცირე ბიზნესი — 500,000 GEL
    "small_business_rate_low":  0.01,   # 1% (500k-მდე)
    "small_business_rate_high": 0.03,   # 3% (500k-ზე)
    "dividend_withholding":     0.05,   # დივიდენდი 5%
    "interest_withholding":     0.05,   # პროცენტი 5%
    "pension_employer":         0.02,   # საპენსიო დამსაქმებელი 2%
    "pension_employee":         0.02,   # საპენსიო დასაქმებული 2%
    "property_tax_max":         0.01,   # ქონების გადასახადი მაქს 1%
}

# VAT exempt operations (მუხლი 167 — ჩათვლის უფლების გარეშე)
VAT_EXEMPT_OPERATIONS = [
    "financial_services",       # ფინანსური მომსახურება
    "medical_services",         # სამედიცინო
    "educational_services",     # განათლება
    "insurance_services",       # სადაზღვევო
    "real_estate_residential",  # საცხოვრებელი უძრავი ქონება
    "postal_services",          # საფოსტო
    "funeral_services",         # სამარხვო
    "lottery",                  # ლატარია
]

# VAT zero-rated (0%) — ჩათვლის უფლებით
VAT_ZERO_RATED = [
    "export_goods",             # ექსპორტი
    "international_transport",  # საერთაშ. ტრანსპორტი
    "diplomatic_missions",      # დიპლომატიური მისიები
]
