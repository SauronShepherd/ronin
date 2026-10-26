"""S3 JSON connector write/read contract against a real S3-compatible service."""

from __future__ import annotations

import hashlib
import os
from typing import Any, cast
from uuid import uuid4

import pytest
from studio_connectors import ConnectorReadResult, ConnectorRegistry, S3JsonConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, FieldSchema
from studio_storage import EnvironmentSecretResolver


class _LoseFirstPutResponse:
    """Simulate a lost response after the S3 service has accepted the first PUT."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.put_attempts = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.put_attempts += 1
        response = self._client.put_object(**kwargs)
        if self.put_attempts == 1:
            raise TimeoutError("simulated response loss after provider commit")
        return cast(dict[str, Any], response)


def test_s3_json_sink_put_read_and_retry_round_trip() -> None:
    endpoint = os.environ.get("RONIN_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("RONIN_TEST_S3_ENDPOINT is required for S3-compatible connector integration")
    boto3 = pytest.importorskip("boto3", reason="boto3 is required for S3 integration")
    from botocore.config import Config  # type: ignore[import-untyped]

    bucket = f"ronin-s3-json-qualification-{uuid4().hex}"
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
        config=Config(s3={"addressing_style": "path"}),
    )
    prefix = "ronin-connector-qualification"
    connection = ConnectionDefinition(
        ConnectionId("s3-qualification"),
        "S3 qualification",
        "s3.json",
        options=(("bucket", bucket), ("prefix", prefix), ("addressing_style", "path")),
    )
    asset = AssetHandle(connection.id, (prefix,), "output.json")
    result = ConnectorReadResult(
        (FieldSchema("id", "integer"), FieldSchema("name", "string")),
        ({"id": 1, "name": "ronin"}, {"id": 2, "name": "dog"}),
    )
    lossy_client = _LoseFirstPutResponse(client)
    connector = S3JsonConnector(client=lossy_client)
    registry = ConnectorRegistry((connector,))
    resolver = EnvironmentSecretResolver({})
    bucket_created = False
    try:
        client.create_bucket(Bucket=bucket)
        bucket_created = True
        with pytest.raises(TimeoutError, match="simulated response loss"):
            registry.write(
                "s3.json",
                connection,
                asset,
                result,
                resolver,
                idempotency_key="qualification-retry-1",
            )
        retry = registry.write(
            "s3.json",
            connection,
            asset,
            result,
            resolver,
            idempotency_key="qualification-retry-1",
        )
        stored = client.get_object(Bucket=bucket, Key=f"{prefix}/output.json")["Body"].read()
        metadata = client.head_object(Bucket=bucket, Key=f"{prefix}/output.json")["Metadata"]
        readback = connector.read(connection, asset, resolver, limit=10)
        discovery_page = connector.discover_page(connection, resolver, page_size=1000)
        discovered_assets = connector.discover(connection, resolver)

        assert retry.output_id == f"s3://{bucket}/{prefix}/output.json"
        assert retry.output_digest == hashlib.sha256(stored).hexdigest()
        assert retry.delivery_semantics == "at_least_once"
        assert retry.idempotency_enforced is False
        assert lossy_client.put_attempts == 2
        assert stored == b'[{"id":1,"name":"ronin"},{"id":2,"name":"dog"}]'
        assert metadata["ronin-output-sha256"] == retry.output_digest
        assert metadata["ronin-idempotency-key-sha256"]
        assert "qualification-retry-1" not in repr(metadata)
        assert readback.rows == result.rows
        assert len(discovery_page.items) == 1
        assert discovery_page.items[0].handle == asset
        assert discovered_assets == discovery_page.items
    finally:
        if bucket_created:
            client.delete_object(Bucket=bucket, Key=f"{prefix}/output.json")
            client.delete_bucket(Bucket=bucket)
