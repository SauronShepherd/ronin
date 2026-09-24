"""Ronin-owned provider-neutral query execution contracts."""

from .contracts import (
    QUERY_ENGINE_NAMESPACE,
    QUERY_ENGINE_VERSION,
    CancellationResult,
    EngineCapabilities,
    EngineHandshake,
    QueryEvidence,
    QueryEngineTransport,
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
from .trino import HttpClient, QueryFailure, TrinoHttpTransport

__all__ = [
    "CancellationResult",
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
    "LocalSqlTransport",
    "QueryState",
    "QueryStatus",
    "QUERY_ENGINE_NAMESPACE",
    "QUERY_ENGINE_VERSION",
    "TranslationPolicy",
    "TrinoHttpTransport",
    "discover_engine",
]
