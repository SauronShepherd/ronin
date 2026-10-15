import pytest
from studio_query_engine import QueryFluxDiscovery, discover_engine


class _Client:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses

    def get_json(self, path: str) -> object:
        return self.responses[path]


def _client() -> _Client:
    return _Client(
        {
            "/health": {
                "healthy": True,
                "version": "provider-1",
                "capabilities": {"cancel": True, "joins": None},
            },
            "/engines": {"engines": ["trino", "duckdb"]},
            "/cluster": {"id": "cluster-1", "state": "ready"},
        }
    )


def test_discovery_preserves_unknown_capabilities_and_metadata() -> None:
    discovered = discover_engine(_client(), provider_id="optional-provider")

    assert discovered.handshake.provider_id == "optional-provider"
    assert discovered.handshake.capabilities.get("joins") is None
    assert discovered.engines == ("duckdb", "trino")
    assert discovered.cluster_state == "ready"


def test_queryflux_discovery_uses_ronin_provider_identity_and_configured_paths() -> None:
    client = _client()
    discovered = QueryFluxDiscovery(
        client,
        health_path="/qf/health",
        registry_path="/qf/engines",
        cluster_path="/qf/cluster",
    )
    client.responses = {
        "/qf/health": client.responses["/health"],
        "/qf/engines": client.responses["/engines"],
        "/qf/cluster": client.responses["/cluster"],
    }
    result = discovered.discover()
    assert result.handshake.provider_id == "queryflux"
    assert result.handshake.cluster_id == "cluster-1"
    assert result.handshake.capabilities.get("joins") is None


@pytest.mark.parametrize(
    ("response", "message"),
    [
        ({"healthy": "yes", "version": "1"}, "healthy"),
        ({"healthy": True, "version": ""}, "version"),
    ],
)
def test_discovery_rejects_invalid_health(response: dict[str, object], message: str) -> None:
    client = _client()
    client.responses["/health"] = response
    with pytest.raises(ValueError, match=message):
        discover_engine(client, provider_id="provider")


def test_discovery_rejects_missing_registry_and_cluster_state() -> None:
    client = _client()
    client.responses["/engines"] = {"engines": []}
    with pytest.raises(ValueError, match="registry"):
        discover_engine(client, provider_id="provider")

    client = _client()
    client.responses["/cluster"] = {"state": ""}
    with pytest.raises(ValueError, match="cluster"):
        discover_engine(client, provider_id="provider")


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        ("/engines", {"engines": [" duckdb"]}, "registry"),
        ("/cluster", {"state": " ready"}, "cluster"),
    ],
)
def test_discovery_rejects_noncanonical_identity_text(
    path: str, value: dict[str, object], message: str
) -> None:
    client = _client()
    client.responses[path] = value
    with pytest.raises(ValueError, match=message):
        discover_engine(client, provider_id="provider")
