from app.api.connectors.balance_connector_demo import BalanceDemoConnector
from app.api.connectors.balance_connector_real import BalanceRealConnector
from app.api.connectors.oris_connector_demo import OrisDemoConnector
from app.api.connectors.oris_connector_real import OrisRealConnector
from app.api.connectors.onec_connector_demo import OneCDemoConnector
from app.api.connectors.onec_connector_real import OneCRealConnector


def get_connector(source_system: str, mode: str = "demo"):
    source = (source_system or "").strip().lower()
    mode = (mode or "demo").strip().lower()

    if source == "balance":
        return BalanceDemoConnector() if mode == "demo" else BalanceRealConnector()

    if source == "oris":
        return OrisDemoConnector() if mode == "demo" else OrisRealConnector()

    if source in ("1c", "onec"):
        return OneCDemoConnector() if mode == "demo" else OneCRealConnector()

    raise ValueError(f"Unsupported source_system: {source_system}")