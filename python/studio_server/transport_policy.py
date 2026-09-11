"""Shared transport policy for Ronin's plaintext HTTP server and CLI client."""

from __future__ import annotations

import ipaddress
from typing import Literal, cast

BindPolicy = Literal["loopback", "container-internal", "insecure-plaintext-network"]
BIND_POLICIES: tuple[BindPolicy, ...] = (
    "loopback",
    "container-internal",
    "insecure-plaintext-network",
)


def parse_bind_policy(value: str | None) -> BindPolicy:
    """Validate one deployment binding policy, defaulting to loopback-only."""
    if value is None:
        return "loopback"
    if value not in BIND_POLICIES:
        allowed = ", ".join(BIND_POLICIES)
        raise ValueError(f"RONIN_BIND_POLICY must be one of: {allowed}")
    return cast(BindPolicy, value)


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


def allows_plaintext_non_loopback(policy: BindPolicy) -> bool:
    """Return whether the declared topology permits non-loopback plaintext HTTP."""
    return policy in {"container-internal", "insecure-plaintext-network"}


__all__ = (
    "BIND_POLICIES",
    "BindPolicy",
    "allows_plaintext_non_loopback",
    "is_loopback_host",
    "parse_bind_policy",
)
