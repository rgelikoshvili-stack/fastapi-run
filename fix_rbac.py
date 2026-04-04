with open("app/api/middleware/rbac_middleware.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    '        "/tenants/",\n    )',
    '        "/tenants/",\n        "/auth/",\n        "/balance-ge/",\n        "/erp-connectors/",\n        "/search/",\n        "/reports/",\n        "/dashboard/",\n        "/ui/",\n    )'
)

with open("app/api/middleware/rbac_middleware.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
