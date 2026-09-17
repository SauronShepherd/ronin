"""Provider-neutral closed vocabulary for plaintext transport topology."""

from __future__ import annotations

from typing import Literal, cast

BindPolicy = Literal["loopback", "container-internal", "insecure-plaintext-network"]
BIND_POLICIES: tuple[BindPolicy, ...] = (
    "loopback",
    "container-internal",
    "insecure-plaintext-network",
)


def parse_bind_policy(value: str | None) -> BindPolicy:
    if value is None:
        return "loopback"
    if value not in BIND_POLICIES:
        raise ValueError(f"RONIN_BIND_POLICY must be one of: {', '.join(BIND_POLICIES)}")
    return cast(BindPolicy, value)


def allows_plaintext_non_loopback(policy: BindPolicy) -> bool:
    return policy in {"container-internal", "insecure-plaintext-network"}


__all__ = (
    "BIND_POLICIES",
    "BindPolicy",
    "allows_plaintext_non_loopback",
    "parse_bind_policy",
)
