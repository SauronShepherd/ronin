"""Ronin-owned provider-neutral query execution contracts."""

from .contracts import (
    DEFAULT_MAX_RESULT_BYTES,
    MAX_RESULT_BYTES,
    QUERY_ENGINE_NAMESPACE,
    QUERY_ENGINE_VERSION,
    CancellationResult,
    EngineCapabilities,
    EngineHandshake,
    QueryEngineTransport,
    QueryEvidence,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryState,
    QueryStatus,
    TranslationPolicy,
)
from .discovery import DiscoveredEngine, DiscoveryClient, discover_engine
from .local import LocalSqlTransport
from .policy import QueryExecutionPolicy
from .queryflux import QueryFluxDiscovery, QueryFluxTrinoTransport
from .trino import HttpClient, QueryFailure, TrinoHttpTransport

__all__ = [
    "CancellationResult",
    "DEFAULT_MAX_RESULT_BYTES",
    "DiscoveredEngine",
    "DiscoveryClient",
    "EngineCapabilities",
    "EngineHandshake",
    "HttpClient",
    "QueryEvidence",
    "QueryEngineTransport",
    "QueryHandle",
    "QueryRequest",
    "QueryResultPage",
    "QueryFailure",
    "QueryExecutionPolicy",
    "QueryFluxDiscovery",
    "QueryFluxTrinoTransport",
    "LocalSqlTransport",
    "MAX_RESULT_BYTES",
    "QueryState",
    "QueryStatus",
    "QUERY_ENGINE_NAMESPACE",
    "QUERY_ENGINE_VERSION",
    "TranslationPolicy",
    "TrinoHttpTransport",
    "discover_engine",
]
