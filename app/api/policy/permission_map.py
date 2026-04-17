PERMISSION_MAP = [
    # Reports
    ("GET", "/reports", "reports:read"),

    # Posting
    ("GET", "/posting", "posting:read"),
    ("POST", "/posting", "posting:write"),

    # Approval
    ("GET", "/approval", "approval:read"),
    ("POST", "/approval", "approval:write"),

    # Payroll
    ("GET", "/payroll", "payroll:read"),
    ("POST", "/payroll", "payroll:write"),
]
