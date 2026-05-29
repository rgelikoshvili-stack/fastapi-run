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

    # ── Opening Balances ─────────────────────────────────────────────────────
    ("GET",    "/opening-balances",    "reports:read"),
    ("PUT",    "/opening-balances",    "posting:write"),
    ("DELETE", "/opening-balances",    "posting:write"),

    # ── Company Identity ──────────────────────────────────────────────────────
    ("GET",    "/company-identity",    "reports:read"),
    ("PUT",    "/company-identity",    "posting:write"),
    ("POST",   "/company-identity",    "posting:write"),

    # ── Evidence Workbench ────────────────────────────────────────────────────
    ("GET",    "/evidence-workbench",  "audit:read"),
    ("POST",   "/evidence-workbench",  "audit:read"),

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

    # ── Metrics (Prometheus — internal only) ─────────────────────────────────
    ("GET",    "/metrics",            "dashboard:admin"),

    # ── Debug (admin/system diagnostics — tenants:manage only) ───────────────
    ("*",      "/debug",              "tenants:manage"),

    # ── Tenants / Admin ───────────────────────────────────────────────────────
    ("*",      "/tenants",            "tenants:manage"),
    ("*",      "/system",             "tenants:manage"),
    ("*",      "/rbac",               "tenants:manage"),
    ("*",      "/vault/credentials",  "tenants:manage"),

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

def _compile_permission_map(permission_map=PERMISSION_MAP):
    """
    Precompute method buckets while preserving PERMISSION_MAP declaration order.

    For each concrete method we include both exact-method entries and wildcard
    entries in their original order, so match_permission() remains behaviorally
    identical to the old linear scan but avoids walking unrelated method rows.
    """
    methods = {method for method, _, _ in permission_map if method != "*"}
    compiled = {}
    for method in methods:
        compiled[method] = [
            (prefix, permission)
            for allowed_method, prefix, permission in permission_map
            if allowed_method == "*" or allowed_method == method
        ]
    compiled["*"] = [
        (prefix, permission)
        for allowed_method, prefix, permission in permission_map
        if allowed_method == "*"
    ]
    return compiled


COMPILED_PERMISSION_MAP = _compile_permission_map()


def match_permission(method: str, path: str):
    """Return the first permission matching method/path, preserving PERMISSION_MAP behavior."""
    for prefix, permission in COMPILED_PERMISSION_MAP.get(method, COMPILED_PERMISSION_MAP.get("*", ())) :
        if path.startswith(prefix):
            return permission
    return None


def linear_match_permission(method: str, path: str):
    """Reference implementation for tests and behavior comparisons."""
    for allowed_method, prefix, permission in PERMISSION_MAP:
        if (allowed_method == "*" or method == allowed_method) and path.startswith(prefix):
            return permission
    return None
