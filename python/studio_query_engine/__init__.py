"""Ronin-owned provider-neutral query execution contracts."""

from .contracts import (
    CancellationResult,
    EngineCapabilities,
    EngineHandshake,
    QueryEvidence,
    QueryHandle,
    QueryRequest,
    QueryResultPage,
    QueryState,
    QueryStatus,
    QUERY_ENGINE_NAMESPACE,
    QUERY_ENGINE_VERSION,
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
