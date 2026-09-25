from __future__ import annotations

import pytest

from studio_data_engineering import QueryEngineRuntimeProvider
from studio_query_engine import (
    DiscoveredEngine,
    EngineCapabilities,
    EngineHandshake,
    QueryExecutionPolicy,
    QueryRequest,
)


def _provider() -> QueryEngineRuntimeProvider:
    discovered = DiscoveredEngine(
        EngineHandshake(
            "optional-query-provider",
            "1.0",
            EngineCapabilities((("cancel", True), ("strict_translation", True))),
            True,
        ),
        ("duckdb",),
        "ready",
    )
    return QueryEngineRuntimeProvider(
        discovered,
        QueryExecutionPolicy((("local", ("duckdb",)),), required_capability="cancel"),
    )


def test_query_engine_provider_implements_runtime_port_and_authorizes_request() -> None:
    provider = _provider()
    handshake = provider.handshake()

    assert handshake.runtime == "query-engine"
    assert handshake.supports(("query", "async-lifecycle", "cancel"))
    assert provider.authorize(QueryRequest("SELECT 1", "local"), engine="duckdb") == "duckdb"


def test_query_engine_provider_fails_closed_for_unauthorized_engine() -> None:
    with pytest.raises(PermissionError, match="not authorized"):
        _provider().authorize(QueryRequest("SELECT 1", "local"), engine="trino")
