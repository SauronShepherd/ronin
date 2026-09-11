"""Secure-default public wrapper for the canonical typed-grant HTTP server."""

from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path
from typing import cast

from studio_core import GrantSet
from studio_execution import DurableExecutionService
from studio_server.http import RoninHTTPServer as _RoninHTTPServer
from studio_server.http import _Handler
from studio_server.transport_policy import (
    BindPolicy,
    allows_plaintext_non_loopback,
    is_loopback_host,
    parse_bind_policy,
)
from studio_storage import sqlite_ready

_BIND_POLICY_ENV = "RONIN_BIND_POLICY"


def _bind_policy_from_env() -> BindPolicy:
    return parse_bind_policy(os.environ.get(_BIND_POLICY_ENV))


def _readiness_database_from_env() -> Path:
    return Path(os.environ.get("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()


class _ReadinessHandler(_Handler):
    """Add one non-versioned operational readiness route around the v1 handler."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            super().do_GET()
            return
        server = cast(RoninHTTPServer, self.server)
        ready = server.ready()
        self._write_json(
            HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
            {"status": "ready" if ready else "not_ready"},
        )


class RoninHTTPServer(_RoninHTTPServer):
    """Supported plaintext server with explicit binding and readiness policy."""

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
        self._readiness_database = _readiness_database_from_env()
        super().__init__(server_address, service, token=token, grants=grants)
        self.RequestHandlerClass = _ReadinessHandler

    def ready(self) -> bool:
        """Return readiness without exposing storage details through HTTP."""
        return sqlite_ready(self._readiness_database)


__all__ = ("RoninHTTPServer",)
