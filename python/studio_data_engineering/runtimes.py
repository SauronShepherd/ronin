"""Runtime handshake and capability negotiation for interchangeable engines."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Protocol

from studio_query_engine import DiscoveredEngine, QueryExecutionPolicy, QueryRequest

from .compiler import RUNTIME_CAPABILITIES


@dataclass(frozen=True, slots=True)
class RuntimeHandshake:
    runtime: str
    provider: str
    version: str
    capabilities: frozenset[str]

    def supports(self, required: Collection[str]) -> bool:
        return set(required) <= self.capabilities


class RuntimeProvider(Protocol):
    def handshake(self) -> RuntimeHandshake: ...


class QueryEngineRuntimeProvider:
    """Adapt a discovered optional query engine to the DE runtime port."""

    def __init__(self, discovered: DiscoveredEngine, policy: QueryExecutionPolicy) -> None:
        self._discovered = discovered
        self._policy = policy

    def handshake(self) -> RuntimeHandshake:
        capabilities = frozenset(
            name for name, value in self._discovered.handshake.capabilities.values if value is True
        )
        capabilities |= {"query", "async-lifecycle"}
        return RuntimeHandshake(
            "query-engine",
            self._discovered.handshake.provider_id,
            self._discovered.handshake.provider_version,
            capabilities,
        )

    def authorize(self, request: QueryRequest, *, engine: str) -> str:
        """Authorize the selected engine before a DE execution intent is emitted."""

        return self._policy.select_engine(
            request,
            engine=engine,
            capabilities=self._discovered.handshake.capabilities,
        )


def local_runtime_handshake(runtime: str) -> RuntimeHandshake:
    """Return the registered local contract; no SDK import is required."""
    try:
        capabilities = RUNTIME_CAPABILITIES[runtime]
    except KeyError as exc:
        raise ValueError(f"runtime is not registered: {runtime}") from exc
    providers = {
        "local-preview": ("ronin-preview", "1.0"),
        "spark-connect": ("spark-connect", "4.x"),
        "spark-sdp": ("sdp-studio", "0.1"),
    }
    provider, version = providers[runtime]
    return RuntimeHandshake(runtime, provider, version, capabilities)


def negotiate_runtime(
    runtime: str,
    *,
    required_capabilities: Collection[str] = (),
    providers: Mapping[str, RuntimeProvider] | None = None,
) -> RuntimeHandshake:
    """Fail closed when the selected provider cannot satisfy the pipeline."""
    handshake = (providers or {}).get(runtime)
    result = local_runtime_handshake(runtime) if handshake is None else handshake.handshake()
    missing = sorted(set(required_capabilities) - result.capabilities)
    if missing:
        raise ValueError(f"runtime {runtime} lacks required capabilities: {', '.join(missing)}")
    return result


__all__ = (
    "QueryEngineRuntimeProvider",
    "RuntimeHandshake",
    "RuntimeProvider",
    "local_runtime_handshake",
    "negotiate_runtime",
)
