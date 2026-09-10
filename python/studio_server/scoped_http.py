"""Secure-default public wrapper for the canonical typed-grant HTTP server."""

from __future__ import annotations

import ipaddress
import os

from studio_core import GrantSet
from studio_execution import DurableExecutionService
from studio_server.http import RoninHTTPServer as _RoninHTTPServer

_INSECURE_REMOTE_HTTP_ENV = "RONIN_INSECURE_ALLOW_REMOTE_HTTP"


def _is_loopback_host(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _insecure_remote_http_enabled() -> bool:
    value = os.environ.get(_INSECURE_REMOTE_HTTP_ENV)
    if value is None or value == "0":
        return False
    if value == "1":
        return True
    raise ValueError(f"{_INSECURE_REMOTE_HTTP_ENV} must be 0 or 1 when set")


class RoninHTTPServer(_RoninHTTPServer):
    """Supported plaintext server with fail-closed non-loopback binding."""

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        token: str,
        grants: GrantSet,
    ) -> None:
        host, _port = server_address
        if not _is_loopback_host(host) and not _insecure_remote_http_enabled():
            raise ValueError(
                "Ronin's built-in server is plaintext HTTP; non-loopback binding requires "
                "RONIN_INSECURE_ALLOW_REMOTE_HTTP=1 for an explicit local-development "
                "network. Use an external TLS terminator for remote access."
            )
        super().__init__(server_address, service, token=token, grants=grants)


__all__ = ("RoninHTTPServer",)
