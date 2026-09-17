"""Trusted-host enforcement with a narrow private health-probe allowance."""

from __future__ import annotations

from ipaddress import IPv4Address, IPv4Network, ip_address
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import Receive, Scope, Send

_PRIVATE_IPV4_NETWORKS = (
    IPv4Network("10.0.0.0/8"),
    IPv4Network("172.16.0.0/12"),
    IPv4Network("192.168.0.0/16"),
    IPv4Network("127.0.0.0/8"),
)


class HealthProbeTrustedHostMiddleware(TrustedHostMiddleware):
    """Permit only private-IP GET health probes outside the configured host allowlist."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if _is_private_health_probe(scope):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def _is_private_health_probe(scope: Scope) -> bool:
    if (
        scope["type"] != "http"
        or scope.get("method") != "GET"
        or scope.get("path") != "/api/health"
    ):
        return False
    host_header = Headers(scope=scope).get("host", "")
    try:
        hostname = urlsplit(f"//{host_header}").hostname
        address = ip_address(hostname or "")
    except ValueError:
        return False
    return isinstance(address, IPv4Address) and any(
        address in network for network in _PRIVATE_IPV4_NETWORKS
    )
