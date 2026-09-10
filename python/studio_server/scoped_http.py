"""Typed-grant public server around the evidence-capable HTTP adapter."""

from __future__ import annotations

import hmac
from http.server import ThreadingHTTPServer

from studio_core import GrantSet
from studio_execution import DurableExecutionService
from studio_server.http import DurableHTTPApplication, _Handler


class RoninHTTPServer(ThreadingHTTPServer):
    """Supported HTTP server with one bearer credential and typed effective grants.

    The transport handler owns the public evidence route. Route-level grant enforcement
    remains #161; this class preserves the #52 fail-closed configuration contract.
    """

    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        token: str,
        grants: GrantSet,
    ) -> None:
        if not token or token != token.strip() or "\n" in token or "\r" in token:
            raise ValueError("token must be non-empty, trimmed, and single-line")
        if not grants.grants:
            raise ValueError("bearer token requires at least one typed authorization grant")
        self.application = DurableHTTPApplication(service)
        self._token = token
        self._grants = grants
        try:
            super().__init__(server_address, _Handler)
        except BaseException:
            self.application.close()
            raise

    @property
    def effective_grants(self) -> GrantSet:
        return self._grants

    def authorized(self, authorization: str | None) -> bool:
        prefix = "Bearer "
        return (
            authorization is not None
            and authorization.startswith(prefix)
            and hmac.compare_digest(authorization[len(prefix) :], self._token)
        )

    def server_close(self) -> None:
        try:
            super().server_close()
        finally:
            self.application.close()


__all__ = ("RoninHTTPServer",)
