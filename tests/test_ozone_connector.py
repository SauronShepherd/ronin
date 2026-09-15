import pytest

from studio_connectors import OzoneJsonConnector
from studio_core import ConnectionDefinition, ConnectionId


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
