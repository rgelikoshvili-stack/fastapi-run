PERMISSION_MAP = [
    # ── Reports ──────────────────────────────────────────────────────────────
    ("GET",    "/reports",            "reports:read"),
    ("GET",    "/tax",                "reports:read"),
    ("GET",    "/currency",           "reports:read"),
    ("*",      "/reports/aging",      "reports:read"),
    ("*",      "/financial-statements", "reports:read"),
    ("*",      "/pdf-report",         "reports:read"),

    # ── Posting ───────────────────────────────────────────────────────────────
    ("GET",    "/posting",            "posting:read"),
    ("POST",   "/posting",            "posting:write"),
    ("PATCH",  "/posting",            "posting:write"),
    ("DELETE", "/posting",            "posting:write"),
    ("*",      "/invoice",            "posting:write"),
    ("*",      "/ai-journal",         "posting:write"),
    ("*",      "/decision-engine",    "posting:write"),
    ("*",      "/erp-memory",         "posting:write"),
    ("*",      "/erp-connectors",     "posting:write"),
    ("*",      "/fx",                 "posting:write"),
    ("*",      "/1c",                 "posting:write"),
    ("*",      "/accounting",         "posting:write"),

    # ── Approval ──────────────────────────────────────────────────────────────
    ("GET",    "/approval",           "approval:read"),
    ("POST",   "/approval",           "approval:write"),
    ("PATCH",  "/approval",           "approval:write"),
    ("DELETE", "/approval",           "approval:write"),

    # ── Payroll ───────────────────────────────────────────────────────────────
    ("GET",    "/payroll",            "payroll:read"),
    ("POST",   "/payroll",            "payroll:write"),
    ("PATCH",  "/payroll",            "payroll:write"),
    ("DELETE", "/payroll",            "payroll:write"),
    ("GET",    "/employees",          "payroll:read"),
    ("POST",   "/employees",          "payroll:write"),
    ("PATCH",  "/employees",          "payroll:write"),
    ("DELETE", "/employees",          "payroll:write"),

    # ── OCR / Documents ───────────────────────────────────────────────────────
    ("GET",    "/ocr",                "ocr:read"),
    ("POST",   "/ocr",                "ocr:write"),
    ("GET",    "/documents",          "ocr:read"),
    ("POST",   "/documents",          "ocr:write"),
    ("PATCH",  "/documents",          "ocr:write"),
    ("DELETE", "/documents",          "ocr:write"),

    # ── Bank / Reconciliation ─────────────────────────────────────────────────
    ("*",      "/bank-csv",           "bank:upload"),
    ("*",      "/bank-accounts",      "bank:upload"),
    ("*",      "/balance-ge",         "bank:process"),
    ("*",      "/bank-sync",          "bank:process"),
    ("GET",    "/reconciliation",     "bank:process"),
    ("POST",   "/reconciliation",     "bank:process"),
    ("PATCH",  "/reconciliation",     "bank:process"),

    # ── Export ────────────────────────────────────────────────────────────────
    ("*",      "/export",             "export:any"),

    # ── Notifications ─────────────────────────────────────────────────────────
    ("GET",    "/notifications",      "notifications:read"),
    ("POST",   "/notifications",      "notifications:write"),
    ("PATCH",  "/notifications",      "notifications:write"),
    ("DELETE", "/notifications",      "notifications:write"),

    # ── Search ────────────────────────────────────────────────────────────────
    ("GET",    "/search",             "search:read"),
    ("POST",   "/search",             "search:read"),

    # ── Inventory ─────────────────────────────────────────────────────────────
    ("GET",    "/inventory",          "inventory:read"),
    ("POST",   "/inventory",          "inventory:write"),
    ("PATCH",  "/inventory",          "inventory:write"),
    ("PUT",    "/inventory",          "inventory:write"),
    ("DELETE", "/inventory",          "inventory:write"),

    # ── Fixed Assets ──────────────────────────────────────────────────────────
    ("GET",    "/fixed-assets",       "assets:read"),
    ("POST",   "/fixed-assets",       "assets:write"),
    ("PATCH",  "/fixed-assets",       "assets:write"),
    ("PUT",    "/fixed-assets",       "assets:write"),
    ("DELETE", "/fixed-assets",       "assets:write"),

    # ── Budget / Cost Centers ─────────────────────────────────────────────────
    ("GET",    "/budget",             "budget:read"),
    ("POST",   "/budget",             "budget:write"),
    ("PATCH",  "/budget",             "budget:write"),
    ("DELETE", "/budget",             "budget:write"),
    ("GET",    "/cost-centers",       "budget:read"),
    ("POST",   "/cost-centers",       "budget:write"),
    ("PATCH",  "/cost-centers",       "budget:write"),
    ("DELETE", "/cost-centers",       "budget:write"),
    ("*",      "/expense-articles",   "budget:write"),

    # ── CRM / Contracts / Invoices / Outgoing ─────────────────────────────────
    ("GET",    "/crm",                "crm:read"),
    ("POST",   "/crm",                "crm:write"),
    ("PATCH",  "/crm",                "crm:write"),
    ("DELETE", "/crm",                "crm:write"),
    ("GET",    "/contracts",          "crm:read"),
    ("POST",   "/contracts",          "crm:write"),
    ("PATCH",  "/contracts",          "crm:write"),
    ("DELETE", "/contracts",          "crm:write"),
    ("GET",    "/invoices",           "crm:read"),
    ("POST",   "/invoices",           "crm:write"),
    ("PATCH",  "/invoices",           "crm:write"),
    ("DELETE", "/invoices",           "crm:write"),
    ("GET",    "/outgoing",           "crm:read"),
    ("POST",   "/outgoing",           "crm:write"),
    ("PATCH",  "/outgoing",           "crm:write"),
    ("*",      "/email-invoice",      "crm:write"),
    ("GET",    "/client",             "crm:read"),
    ("POST",   "/client",             "crm:write"),

    # ── Expenses ──────────────────────────────────────────────────────────────
    ("GET",    "/expenses",           "posting:read"),
    ("POST",   "/expenses",           "posting:write"),
    ("PATCH",  "/expenses",           "posting:write"),
    ("DELETE", "/expenses",           "posting:write"),

    # ── Patterns / Learning ───────────────────────────────────────────────────
    ("GET",    "/patterns",           "patterns:view"),
    ("POST",   "/patterns",           "patterns:manage"),
    ("PATCH",  "/patterns",           "patterns:manage"),
    ("DELETE", "/patterns",           "patterns:manage"),
    ("GET",    "/learning",           "patterns:view"),
    ("POST",   "/learning",           "patterns:manage"),
    ("DELETE", "/learning",           "patterns:manage"),
    ("GET",    "/transaction-memory", "patterns:view"),
    ("POST",   "/transaction-memory", "patterns:manage"),
    ("DELETE", "/transaction-memory", "patterns:manage"),
    ("GET",    "/transaction-ai",     "chat:use"),
    ("POST",   "/transaction-ai",     "chat:use"),

    # ── Audit ─────────────────────────────────────────────────────────────────
    ("GET",    "/audit",              "audit:view"),
    ("GET",    "/audit-log",          "audit:read"),
    ("GET",    "/audit-engine",       "audit:view"),
    ("GET",    "/audit-trail",        "audit:read"),
    ("GET",    "/qa",                 "audit:view"),
    ("GET",    "/docs-hub",           "audit:read"),

    # ── Tenants / Admin ───────────────────────────────────────────────────────
    ("*",      "/tenants",            "tenants:manage"),
    ("*",      "/system",             "tenants:manage"),
    ("*",      "/rbac",               "tenants:manage"),

    # ── Settings / Integrations ───────────────────────────────────────────────
    ("*",      "/security",           "settings:write"),
    ("*",      "/integrations",       "settings:write"),
    ("*",      "/webhooks",           "settings:write"),
    ("*",      "/email-collector",    "settings:write"),
    ("*",      "/balance-credentials","settings:write"),
    ("*",      "/rsge-credentials",   "settings:write"),
    ("*",      "/api-docs",           "settings:write"),

    # ── Chat / Collaboration ──────────────────────────────────────────────────
    ("*",      "/chat",               "chat:use"),
    ("*",      "/collaboration",      "chat:use"),

    # ── Dashboard (write operations only, reads are public) ───────────────────
    ("POST",   "/dashboard",          "dashboard:view"),
    ("DELETE", "/dashboard",          "dashboard:admin"),
]
