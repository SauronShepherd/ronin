"""Typed-grant wrapper for the v0.1 HTTP adapter."""

from __future__ import annotations

from studio_core import GrantSet
from studio_execution import DurableExecutionService
from studio_server.http import RoninHTTPServer as _EvidenceHTTPServer


class RoninHTTPServer(_EvidenceHTTPServer):
    """Bind validated typed grants to the static bearer credential.

    Route-level scoped enforcement remains owned by #161; this wrapper preserves
    the #52 effective-grant contract while the HTTP adapter exposes public evidence.
    """

    def __init__(
        self,
        server_address: tuple[str, int],
        service: DurableExecutionService,
        *,
        token: str,
        grants: GrantSet,
    ) -> None:
        if not grants.grants:
            raise ValueError("bearer token requires at least one typed authorization grant")
        self._grants = grants
        super().__init__(server_address, service, token=token)

    @property
    def effective_grants(self) -> GrantSet:
        return self._grants


__all__ = ("RoninHTTPServer",)
