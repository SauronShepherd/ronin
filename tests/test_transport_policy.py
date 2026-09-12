from __future__ import annotations

import pytest

from studio_cli.network import ControlPlaneClient
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


@pytest.mark.parametrize(
    "host",
    [None, "server", "0.0.0.0", "192.168.1.10", "example.test"],  # noqa: S104  # deliberate non-loopback sentinel
)
def test_loopback_host_rejects_non_loopback_targets(host: str | None) -> None:
    assert not is_loopback_host(host)


def test_client_defaults_to_rejecting_non_loopback_plaintext(monkeypatch) -> None:
    monkeypatch.delenv("RONIN_BIND_POLICY", raising=False)
    with pytest.raises(ValueError, match="requires HTTPS"):
        ControlPlaneClient("http://server:8080", "token")


def test_client_accepts_supported_container_internal_plaintext(monkeypatch) -> None:
    monkeypatch.setenv("RONIN_BIND_POLICY", "container-internal")
    client = ControlPlaneClient("http://server:8080", "token")
    assert client.bind_policy == "container-internal"


def test_client_accepts_https_under_default_policy(monkeypatch) -> None:
    monkeypatch.delenv("RONIN_BIND_POLICY", raising=False)
    client = ControlPlaneClient("https://example.test", "token")
    assert client.bind_policy == "loopback"


def test_client_rejects_invalid_environment_policy(monkeypatch) -> None:
    monkeypatch.setenv("RONIN_BIND_POLICY", "remote")
    with pytest.raises(ValueError, match="RONIN_BIND_POLICY must be one of"):
        ControlPlaneClient("https://example.test", "token")
