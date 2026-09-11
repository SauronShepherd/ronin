"""Secure-default public wrapper for the canonical typed-grant HTTP server."""

from __future__ import annotations

import os

from studio_core import GrantSet
from studio_execution import DurableExecutionService
from studio_server.http import RoninHTTPServer as _RoninHTTPServer
from studio_server.transport_policy import (
    BindPolicy,
    allows_plaintext_non_loopback,
    is_loopback_host,
    parse_bind_policy,
)

_BIND_POLICY_ENV = "RONIN_BIND_POLICY"


def _bind_policy_from_env() -> BindPolicy:
    return parse_bind_policy(os.environ.get(_BIND_POLICY_ENV))


class RoninHTTPServer(_RoninHTTPServer):
    """Supported plaintext server with explicit fail-closed binding policy."""

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        token: str,
        grants: GrantSet,
    ) -> None:
        host, _port = server_address
        policy = _bind_policy_from_env()
        if not is_loopback_host(host) and not allows_plaintext_non_loopback(policy):
            raise ValueError(
                "Ronin's built-in server is plaintext HTTP; non-loopback binding requires "
                "RONIN_BIND_POLICY=container-internal for the supported private Compose "
                "bridge, or RONIN_BIND_POLICY=insecure-plaintext-network for an explicit "
                "trusted development network. Use an external TLS terminator for remote access."
            )
        super().__init__(server_address, service, token=token, grants=grants)


__all__ = ("RoninHTTPServer",)
