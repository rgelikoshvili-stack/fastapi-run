from decimal import Decimal

CHART_OF_ACCOUNTS = {
    '1110': 'Cash and Cash Equivalents',
    '1210': 'Accounts Receivable',
    '1310': 'Inventory',
    '2110': 'Accounts Payable',
    '2210': 'Short-term Loans',
    '3110': 'Share Capital',
    '4110': 'Revenue from Sales',
    '4210': 'Other Income',
    '5210': 'Salaries Expense',
    '5310': 'Rent Expense',
    '5410': 'Utilities Expense',
    '5510': 'Marketing Expense',
    '5610': 'Bank Charges',
    '5710': 'Tax Expense',
    '5810': 'Depreciation',
    '6110': 'VAT Payable',
    '6120': 'Income Tax Payable',
}

ACCOUNT_RULES = [
    {'keywords': ['salary','salaries','ხელფასი','პრემია','payroll'], 'debit': '5210', 'credit': '1110', 'vat': 'exempt',   'confidence': 0.95},
    {'keywords': ['rent','იჯარა','ქირა'],                             'debit': '5310', 'credit': '2110', 'vat': 'standard', 'confidence': 0.95},
    {'keywords': ['utility','electric','water','gas','communal'],     'debit': '5410', 'credit': '2110', 'vat': 'standard', 'confidence': 0.92},
    {'keywords': ['marketing','advertising','რეკლამა'],               'debit': '5510', 'credit': '2110', 'vat': 'standard', 'confidence': 0.90},
    {'keywords': ['bank','commission','საბანკო','მომსახურება'],       'debit': '5610', 'credit': '1110', 'vat': 'exempt',   'confidence': 0.95},
    {'keywords': ['tax','გადასახადი','rs.ge','revenue service'],      'debit': '5710', 'credit': '6120', 'vat': 'exempt',   'confidence': 0.95},
    {'keywords': ['invoice','ანგარიშფაქტურა','supplier','მომწოდებ'], 'debit': '1310', 'credit': '2110', 'vat': 'standard', 'confidence': 0.85},
    {'keywords': ['income','revenue','გაყიდვა','receipt'],            'debit': '1110', 'credit': '4110', 'vat': 'standard', 'confidence': 0.88},
]

def get_account_rules(description: str, counterparty: str = '') -> dict | None:
    text = f"{description} {counterparty}".lower()
    for rule in ACCOUNT_RULES:
        if any(kw in text for kw in rule['keywords']):
            return {
                'debit_account':       rule['debit'],
                'debit_account_name':  CHART_OF_ACCOUNTS.get(rule['debit'], ''),
                'credit_account':      rule['credit'],
                'credit_account_name': CHART_OF_ACCOUNTS.get(rule['credit'], ''),
                'tax_hint':            'VAT_18' if rule['vat'] == 'standard' else 'EXEMPT',
                'confidence':          rule['confidence'],
                'reasoning':           f"Rule match: {rule['keywords'][0]}",
            }
    return None

def load_chart_of_accounts() -> dict:
    return CHART_OF_ACCOUNTS
