"""Shared transport policy for Ronin's plaintext HTTP server and CLI client."""

from __future__ import annotations

import ipaddress

from studio_core.transport_policy import (
    BIND_POLICIES,
    BindPolicy,
    allows_plaintext_non_loopback,
    parse_bind_policy,
)


def is_loopback_host(hostname: str | None) -> bool:
    """Return whether a literal URL/server host is an explicit loopback target."""
    if hostname is None:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


__all__ = (
    "BIND_POLICIES",
    "BindPolicy",
    "allows_plaintext_non_loopback",
    "is_loopback_host",
    "parse_bind_policy",
)
