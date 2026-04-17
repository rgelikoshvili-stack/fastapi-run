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

    # OCR
    ("GET", "/ocr", "ocr:read"),
    ("POST", "/ocr", "ocr:write"),

    # Notifications
    ("GET", "/notifications", "notifications:read"),
    ("POST", "/notifications", "notifications:write"),

    # Search
    ("GET", "/search", "search:read"),
    ("POST", "/search", "search:read"),
]