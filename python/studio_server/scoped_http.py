"""Secure-default public wrapper for the canonical typed-grant HTTP server."""

from __future__ import annotations

import os
from http import HTTPStatus
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from studio_core import GrantSet
from studio_execution import DurableExecutionService
from studio_sql import SqlEngine
from studio_storage import sqlite_ready

from studio_server.http import RoninHTTPServer as _RoninHTTPServer
from studio_server.http import _Handler, _single_query_values
from studio_server.transport_policy import (
    BindPolicy,
    allows_plaintext_non_loopback,
    is_loopback_host,
    parse_bind_policy,
)

_BIND_POLICY_ENV = "RONIN_BIND_POLICY"


def _bind_policy_from_env() -> BindPolicy:
    return parse_bind_policy(os.environ.get(_BIND_POLICY_ENV))


def _readiness_database_from_env() -> Path:
    return Path(os.environ.get("RONIN_DB", ".ronin/ronin.sqlite3")).expanduser().resolve()


class _ReadinessHandler(_Handler):
    """Add readiness and public-list authorization around the v1 handler."""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            server = cast(RoninHTTPServer, self.server)
            ready = server.ready()
            self._write_json(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "ready" if ready else "not_ready"},
            )
            return

        split = urlsplit(self.path)
        if split.path == "/v1/jobs":
            try:
                query = _single_query_values(
                    split.query,
                    allowed=frozenset({"project", "state", "limit", "cursor"}),
                )
            except ValueError:
                # Preserve the canonical handler's existing validation/error contract.
                super().do_GET()
                return
            if query.get("project") is None:
                server = cast(RoninHTTPServer, self.server)
                if not server.permits_unfiltered_project_list():
                    self._error(
                        HTTPStatus.FORBIDDEN,
                        "forbidden",
                        "project filter is required for scoped list authorization",
                    )
                    return

        super().do_GET()


class RoninHTTPServer(_RoninHTTPServer):
    """Supported plaintext server with explicit binding and readiness policy."""

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        token: str,
        grants: GrantSet,
        sql_engine: SqlEngine | None = None,
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
        super().__init__(server_address, service, token=token, grants=grants, sql_engine=sql_engine)
        self.RequestHandlerClass = _ReadinessHandler

    def permits_unfiltered_project_list(self) -> bool:
        """Return whether every project is safely listable before choosing a storage page."""
        supported = tuple(
            grant
            for grant in self.effective_grants.grants
            if "list" in grant.actions and not grant.constraints
        )
        project_wildcards = tuple(
            grant
            for grant in supported
            if grant.resource.kind == "project" and grant.resource.identifier is None
        )
        if project_wildcards:
            return len(project_wildcards) == 1
        global_wildcards = tuple(grant for grant in supported if grant.resource.kind == "*")
        return len(global_wildcards) == 1

    def ready(self) -> bool:
        """Return readiness without exposing storage details through HTTP."""
        return sqlite_ready(self._readiness_database)


__all__ = ("RoninHTTPServer",)
