import pytest
from studio_connectors import ConnectorReadResult, ConnectorRegistry, OzoneJsonConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, FieldSchema
from studio_storage import EnvironmentSecretResolver


class _OzoneS3:
    def __init__(self) -> None:
        self.puts: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> dict[str, str]:
        self.puts.append(dict(kwargs))
        return {"ETag": '"ozone-etag"'}


def test_ozone_profile_requires_gateway_endpoint() -> None:
    connection = ConnectionDefinition(
        ConnectionId("ozone"), "Ozone", "ozone.s3.json", options=(("bucket", "data"),)
    )
    with pytest.raises(ValueError, match="endpoint_url"):
        OzoneJsonConnector().discover(connection, None)  # type: ignore[arg-type]


def test_ozone_profile_accepts_http_gateway_for_private_deployment() -> None:
    connection = ConnectionDefinition(
        ConnectionId("ozone"),
        "Ozone",
        "ozone.s3.json",
        options=(("bucket", "data"), ("endpoint_url", "http://om:9878")),
    )
    connector = OzoneJsonConnector(client=object())
    assert connector._config(connection) == ("data", "")


def test_ozone_profile_inherits_fail_closed_at_least_once_sink_contract() -> None:
    client = _OzoneS3()
    connector = OzoneJsonConnector(client=client)
    connection = ConnectionDefinition(
        ConnectionId("ozone"),
        "Ozone",
        "ozone.s3.json",
        options=(
            ("bucket", "data"),
            ("prefix", "exports"),
            ("endpoint_url", "http://om:9878"),
        ),
    )
    registry = ConnectorRegistry((connector,))
    capabilities = connector.descriptor.capabilities
    assert capabilities.write is True
    assert capabilities.transactional_write is False

    receipt = registry.write(
        "ozone.s3.json",
        connection,
        AssetHandle(connection.id, ("exports",), "result.json"),
        ConnectorReadResult((FieldSchema("id", "integer"),), ({"id": 7},)),
        EnvironmentSecretResolver({}),
        idempotency_key="ozone-export-7",
    )

    assert receipt.output_id == "s3://data/exports/result.json"
    assert receipt.commit_id == "ozone-etag"
    assert receipt.transactional is False
    assert receipt.idempotency_enforced is False
    assert receipt.delivery_semantics == "at_least_once"
    assert client.puts[0]["Key"] == "exports/result.json"
    assert client.puts[0]["ContentType"] == "application/json"
