from __future__ import annotations

import pytest

from studio_server.transport_policy import (
    BIND_POLICIES,
    allows_plaintext_non_loopback,
    is_loopback_host,
    parse_bind_policy,
)


def test_binding_policy_defaults_to_loopback_and_has_closed_values() -> None:
    assert parse_bind_policy(None) == "loopback"
    assert BIND_POLICIES == (
        "loopback",
        "container-internal",
        "insecure-plaintext-network",
    )
    assert not allows_plaintext_non_loopback("loopback")
    assert allows_plaintext_non_loopback("container-internal")
    assert allows_plaintext_non_loopback("insecure-plaintext-network")


@pytest.mark.parametrize("value", ["", "remote", "CONTAINER-INTERNAL", " container-internal"])
def test_binding_policy_rejects_unknown_or_noncanonical_values(value: str) -> None:
    with pytest.raises(ValueError, match="RONIN_BIND_POLICY must be one of"):
        parse_bind_policy(value)


@pytest.mark.parametrize("host", ["localhost", "LOCALHOST", "127.0.0.1", "::1"])
def test_loopback_host_recognizes_only_explicit_loopback_targets(host: str) -> None:
    assert is_loopback_host(host)


@pytest.mark.parametrize("host", [None, "server", "0.0.0.0", "192.168.1.10", "example.test"])
def test_loopback_host_rejects_non_loopback_targets(host: str | None) -> None:
    assert not is_loopback_host(host)
