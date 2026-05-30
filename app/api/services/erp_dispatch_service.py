"""app/api/services/erp_dispatch_service.py — Multi-ERP Dispatch Layer (Phase 7).

Unified ERP connector registry with:
  - connector_health_matrix  — health status for all registered connectors
  - get_routing_rules        — per-tenant transaction-type → connector mapping
  - set_routing_rule         — save a routing rule to tenant_settings
  - route_transaction        — resolve which connector to use for a draft
  - get_dispatch_log_summary — aggregate posting log counts by connector/status
"""
from __future__ import annotations

from typing import Any

from app.api.db import get_conn, _q
from app.api.services.tenant_config_service import get_tenant_setting, set_tenant_setting

# All known connectors in this deployment
KNOWN_CONNECTORS: list[str] = ["balance", "1c", "oris"]

# Transaction type categories (maps journal account prefix to type)
TRANSACTION_TYPES = {
    "sales":     "6",   # revenue accounts
    "expenses":  "7",   # expense accounts
    "payroll":   "72",  # salary expense
    "tax":       "33",  # tax payables
    "inventory": "13",  # inventory
}

ROUTING_KEY_PREFIX = "erp_routing"
DEFAULT_CONNECTOR   = "balance"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def infer_transaction_type(account_code: str) -> str:
    """Infer transaction type from an account code prefix."""
    for txn_type, prefix in sorted(TRANSACTION_TYPES.items(), key=lambda x: -len(x[1])):
        if account_code.startswith(prefix):
            return txn_type
    return "default"


def apply_routing_rules(rules: dict[str, str], txn_type: str) -> str:
    """Return the connector for *txn_type* using *rules*, falling back to default."""
    return rules.get(txn_type) or rules.get("default") or DEFAULT_CONNECTOR


# ---------------------------------------------------------------------------
# Connector health (sync connectors — run in thread pool in production)
# ---------------------------------------------------------------------------

def _check_connector_health(name: str, tenant_id: str) -> dict[str, Any]:
    """Check one connector's health. Returns status dict."""
    try:
        if name == "balance":
            from app.api.connectors.balance_connector import BalanceConnector
            conn = BalanceConnector(tenant_id=tenant_id)
        elif name == "1c":
            from app.api.connectors.onec_connector import OneCConnector
            conn = OneCConnector(tenant_id=tenant_id)
        elif name == "oris":
            from app.api.connectors.oris_connector import OrisConnector
            conn = OrisConnector(tenant_id=tenant_id)
        else:
            return {"connector": name, "status": "unknown", "connected": False,
                    "message": f"Unknown connector: {name}"}
        result = conn.status()
        return {
            "connector": name,
            "status":    "ok" if result.get("connected") else "error",
            "connected": bool(result.get("connected")),
            "mode":      result.get("mode", "unknown"),
            "message":   result.get("message", ""),
        }
    except Exception as exc:
        return {"connector": name, "status": "error", "connected": False,
                "message": str(exc)[:120]}


def connector_health_matrix(tenant_id: str) -> dict[str, Any]:
    """Return health status for all known connectors."""
    results = [_check_connector_health(name, tenant_id) for name in KNOWN_CONNECTORS]
    ok_count = sum(1 for r in results if r["connected"])
    return {
        "connectors": results,
        "healthy_count": ok_count,
        "total_count": len(KNOWN_CONNECTORS),
        "all_healthy": ok_count == len(KNOWN_CONNECTORS),
    }


# ---------------------------------------------------------------------------
# Routing rules (stored in tenant_settings)
# ---------------------------------------------------------------------------

async def get_routing_rules(tenant_id: str) -> dict[str, str]:
    """Return the routing rules dict for a tenant.

    Default: all transaction types → DEFAULT_CONNECTOR.
    """
    stored = await get_tenant_setting(tenant_id, ROUTING_KEY_PREFIX, {})
    if not isinstance(stored, dict):
        stored = {}
    rules = {txn_type: DEFAULT_CONNECTOR for txn_type in TRANSACTION_TYPES}
    rules["default"] = DEFAULT_CONNECTOR
    rules.update(stored)
    return rules


async def set_routing_rule(
    tenant_id: str,
    txn_type: str,
    connector: str,
) -> dict[str, str]:
    """Set a routing rule for *txn_type* → *connector*.

    Raises ValueError if txn_type or connector is invalid.
    """
    valid_types = set(TRANSACTION_TYPES.keys()) | {"default"}
    if txn_type not in valid_types:
        raise ValueError(f"INVALID_TXN_TYPE: {txn_type}")
    if connector not in KNOWN_CONNECTORS:
        raise ValueError(f"INVALID_CONNECTOR: {connector}")

    stored = await get_tenant_setting(tenant_id, ROUTING_KEY_PREFIX, {})
    if not isinstance(stored, dict):
        stored = {}
    stored[txn_type] = connector
    await set_tenant_setting(tenant_id, ROUTING_KEY_PREFIX, stored)
    return stored


async def route_transaction(tenant_id: str, account_code: str) -> dict[str, Any]:
    """Determine which connector to use for a transaction with *account_code*."""
    txn_type = infer_transaction_type(account_code)
    rules    = await get_routing_rules(tenant_id)
    connector = apply_routing_rules(rules, txn_type)
    return {
        "account_code":  account_code,
        "txn_type":      txn_type,
        "connector":     connector,
        "routing_rules": rules,
    }


# ---------------------------------------------------------------------------
# Dispatch log summary
# ---------------------------------------------------------------------------

async def get_dispatch_log_summary(
    tenant_id: str,
    limit: int = 10,
) -> dict[str, Any]:
    """Return posting log counts grouped by target_system and status."""
    async with get_conn() as conn:
        rows = await conn.fetch(
            _q("""
                SELECT target_system, status, COUNT(*) AS count
                FROM posting_log
                WHERE tenant_id = $1
                GROUP BY target_system, status
                ORDER BY target_system, status
            """),
            tenant_id,
        )
        recent = await conn.fetch(
            _q("""
                SELECT id, draft_id, target_system, status, created_at, error_message
                FROM posting_log
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """),
            tenant_id, limit,
        )

    by_connector: dict[str, dict] = {}
    for r in rows:
        name = r["target_system"] or "unknown"
        if name not in by_connector:
            by_connector[name] = {"total": 0, "by_status": {}}
        cnt = int(r["count"])
        by_connector[name]["total"] += cnt
        by_connector[name]["by_status"][r["status"]] = cnt

    return {
        "by_connector": by_connector,
        "recent":       [dict(r) for r in recent],
    }
