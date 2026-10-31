"""Rate-limit client identity with an explicit, deny-by-default proxy boundary.

IMPORTANT: the ASGI server must supply the actual socket peer to request.client.
Run Uvicorn with --no-proxy-headers; otherwise server-side header rewriting
can defeat checks performed here. Configure RATE_LIMIT_TRUSTED_PROXY_CIDRS
ONLY after staging has proven the exact immediate ingress peers and ensured
that trusted proxies append/sanitize X-Forwarded-For.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from ipaddress import ip_address, ip_network
from typing import Any

log = logging.getLogger(__name__)

_MAX_HEADER_LENGTH = 1024
_MAX_HOPS = 16
_MAX_PROXY_RANGES = 32


@lru_cache(maxsize=32)
def _trusted_proxy_networks(raw_config: str) -> tuple:
    """Parse a small explicit allowlist. Never trust an internet-wide /0."""
    if not raw_config.strip():
        return ()
    entries = raw_config.split(",")
    if len(entries) > _MAX_PROXY_RANGES or any(not x.strip() for x in entries):
        raise ValueError("invalid trusted proxy allowlist")
    networks = []
    for entry in entries:
        network = ip_network(entry.strip(), strict=False)
        if network.prefixlen == 0:
            raise ValueError("internet-wide trusted proxy ranges are forbidden")
        networks.append(network)
    return tuple(networks)


def _peer_ip(request: Any) -> str:
    """Read socket peer; do not use any HTTP-supplied address for fallback."""
    client = getattr(request, "client", None)
    raw = getattr(client, "host", None)
    if not isinstance(raw, str) or not raw or len(raw) > 128:
        return "unknown"
    try:
        return ip_address(raw).compressed
    except ValueError:
        # TestClient typically supplies "testclient"; preserve this stable
        # non-header host when no numeric socket address is available.
        return raw


def _trusted(address: Any, networks: tuple) -> bool:
    return any(address in network for network in networks)


def _forwarded_headers(request: Any) -> list[str]:
    headers = getattr(request, "headers", None)
    if headers is None:
        return []
    if hasattr(headers, "getlist"):
        return headers.getlist("x-forwarded-for")
    if hasattr(headers, "get"):
        value = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        return [value] if value else []
    return []


def client_ip_for_rate_limit(request: Any) -> str:
    """Return an IP that cannot be selected by an untrusted client header.

    Without explicitly trusted socket peers this always uses the peer.
    From a trusted proxy, traverse a validated XFF chain right-to-left and
    stop at the first untrusted hop. Ignore ambiguous/malformed chains.
    """
    peer = _peer_ip(request)
    try:
        peer_addr = ip_address(peer)
    except ValueError:
        return peer

    config = os.getenv("RATE_LIMIT_TRUSTED_PROXY_CIDRS", "")
    try:
        networks = _trusted_proxy_networks(config)
    except ValueError:
        log.error("rate_limit_proxy_allowlist_invalid_using_socket_peer")
        return peer
    if not networks or not _trusted(peer_addr, networks):
        return peer

    headers = _forwarded_headers(request)
    if len(headers) != 1 or not isinstance(headers[0], str):
        return peer
    header = headers[0]
    if not header or len(header) > _MAX_HEADER_LENGTH:
        return peer
    hops = [item.strip() for item in header.split(",")]
    if not 1 <= len(hops) <= _MAX_HOPS:
        return peer
    try:
        addresses = [ip_address(item) for item in hops]
    except ValueError:
        return peer
    for address in reversed(addresses):
        if not _trusted(address, networks):
            return address.compressed

    # All advertised hops were trusted. Do not let a client supply a fake
    # final identity by claiming to be another trusted proxy.
    return peer
