"""Optional QueryFlux adapters behind Ronin-owned query-engine contracts.

QueryFlux is deliberately represented only at the integration boundary.  The
rest of Ronin observes ``DiscoveredEngine`` and ``QueryEngineTransport`` and
never imports provider response types.
"""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    CancellationResult,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryStatus,
)
from .discovery import DiscoveredEngine, DiscoveryClient, discover_engine
from .trino import HttpClient, TrinoHttpTransport


@dataclass(frozen=True, slots=True)
class QueryFluxDiscovery:
    """Resolve QueryFlux health and routing metadata through a bounded client."""

    client: DiscoveryClient
    health_path: str = "/health"
    registry_path: str = "/engines"
    cluster_path: str = "/cluster"

    def discover(self) -> DiscoveredEngine:
        return discover_engine(
            self.client,
            provider_id="queryflux",
            health_path=self.health_path,
            registry_path=self.registry_path,
            cluster_path=self.cluster_path,
        )


class QueryFluxTrinoTransport:
    """Map QueryFlux's Trino-compatible HTTP endpoint to Ronin's lifecycle port."""

    def __init__(self, client: HttpClient, *, base_url: str) -> None:
        self._transport = TrinoHttpTransport(client, base_url=base_url, provider_id="queryflux")

    def submit(self, request: QueryRequest) -> tuple[QueryHandle, str]:
        return self._transport.submit(request)

    def poll(
        self, handle: QueryHandle, next_uri: str
    ) -> tuple[QueryStatus, QueryResultPage | None, str | None]:
        return self._transport.poll(handle, next_uri)

    def cancel(self, handle: QueryHandle) -> CancellationResult:
        return self._transport.cancel(handle)


__all__ = ("QueryFluxDiscovery", "QueryFluxTrinoTransport")
