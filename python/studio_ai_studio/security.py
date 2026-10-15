"""Network boundary validation for AI Studio endpoints."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class NetworkPolicyError(ValueError):
    """Endpoint violates AI Studio's outbound network policy."""


@dataclass(frozen=True, slots=True)
class NetworkPolicy:
    allow_http: bool = False
    allow_private: bool = False
    allow_loopback: bool = True
    allow_link_local: bool = False
    allowed_hosts: frozenset[str] = frozenset()


def validate_endpoint_url(url: str, policy: NetworkPolicy | None = None) -> str:
    """Validate syntax and resolved addresses without making an HTTP request."""
    config = policy or NetworkPolicy()
    parsed = urlsplit(url)
    schemes = {"https"} | ({"http"} if config.allow_http else set())
    if parsed.scheme not in schemes or not parsed.hostname:
        raise NetworkPolicyError("endpoint must use an allowed scheme and host")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise NetworkPolicyError("endpoint cannot contain credentials, query or fragment")
    host = parsed.hostname.casefold().rstrip(".")
    if config.allowed_hosts and host not in config.allowed_hosts:
        raise NetworkPolicyError("endpoint host is not allowlisted")
    addresses = _resolve(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_link_local and not config.allow_link_local:
            raise NetworkPolicyError("link-local endpoint is blocked")
        if ip.is_loopback and not config.allow_loopback:
            raise NetworkPolicyError("loopback endpoint is blocked")
        if ip.is_private and not config.allow_private and not ip.is_loopback:
            raise NetworkPolicyError("private endpoint is not allowed by policy")
        if ip.is_reserved or ip.is_unspecified or ip.is_multicast:
            raise NetworkPolicyError("reserved endpoint address is blocked")
    return host


def _resolve(host: str, port: int) -> tuple[str, ...]:
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise NetworkPolicyError("endpoint host cannot be resolved") from exc
    addresses = tuple(sorted({str(item[4][0]) for item in results}))
    if not addresses:
        raise NetworkPolicyError("endpoint host has no addresses")
    return addresses


__all__ = ["NetworkPolicy", "NetworkPolicyError", "validate_endpoint_url"]
