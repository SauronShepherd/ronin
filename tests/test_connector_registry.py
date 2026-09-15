import pytest

from studio_connectors import (
    ConnectorRegistry,
    HttpJsonConnector,
    PostgresConnector,
    S3JsonConnector,
    builtin_connector_registry,
)
from studio_core import ConnectionDefinition, ConnectionId
from studio_storage import EnvironmentSecretResolver


def test_builtin_connector_registry_is_explicit() -> None:
    registry = ConnectorRegistry((HttpJsonConnector(), PostgresConnector(), S3JsonConnector()))
    assert registry.ids() == ("http.json", "postgresql", "s3.json")
    assert registry.require("http.json").descriptor.capabilities.read
    assert registry.require("postgresql").descriptor.capabilities.discover
    with pytest.raises(KeyError):
        registry.require("unknown")


def test_connector_registry_rejects_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        ConnectorRegistry((HttpJsonConnector(), HttpJsonConnector()))


def test_builtin_connector_registry_exposes_reference_profiles() -> None:
    assert builtin_connector_registry().ids() == (
        "azure.blob.json",
        "http.json",
        "jdbc",
        "ozone.s3.json",
        "postgresql",
        "s3.json",
    )


def test_http_connector_requires_https_by_default() -> None:
    connector = HttpJsonConnector()
    connection = ConnectionDefinition(
        ConnectionId("http-source"),
        "HTTP source",
        "http.json",
        options=(("base_url", "http://example.test/api"),),
    )
    with pytest.raises(ValueError, match="HTTPS"):
        connector.discover(connection, EnvironmentSecretResolver({}))


def test_http_connector_allows_explicit_local_http_profile() -> None:
    connector = HttpJsonConnector()
    connection = ConnectionDefinition(
        ConnectionId("http-source"),
        "HTTP source",
        "http.json",
        options=(
            ("allow_http", "true"),
            ("base_url", "http://localhost:8080/api"),
        ),
    )
    assert connector.discover(connection, EnvironmentSecretResolver({})) == ()
