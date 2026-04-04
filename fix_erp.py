with open("app/api/services/erp_history_import_service.py", "r", encoding="utf-8") as f:
    content = f.read()

old = """from typing import Any, Dict, Optional
from app.api.connectors.connector_factory import get_connector
from app.api.services.erp_import_service import import_erp_history"""

new = """from typing import Any, Dict, Optional
from app.api.connectors.balance_connector import BalanceConnector
from app.api.connectors.onec_connector import OneCConnector
from app.api.services.erp_import_service import import_erp_history

def get_connector(source_system: str, mode: str = "demo"):
    if source_system == "balance":
        return BalanceConnector()
    elif source_system == "1c":
        return OneCConnector()
    else:
        class _DemoConnector:
            def fetch_posted_history(self, **kwargs):
                return []
        return _DemoConnector()"""

content = content.replace(old, new, 1)

with open("app/api/services/erp_history_import_service.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
