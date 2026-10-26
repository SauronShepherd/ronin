from __future__ import annotations

import hashlib
from typing import cast

import pytest
from studio_connectors import (
    ConnectorCapabilityError,
    ConnectorReadResult,
    ConnectorRegistry,
    S3JsonConnector,
)
from studio_core import (
    AssetHandle,
    ConnectionDefinition,
    ConnectionId,
    FieldSchema,
    SourceCheckpoint,
)
from studio_storage import EnvironmentSecretResolver


class _Body:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self, limit: int) -> bytes:
        return self.value[:limit]


class _S3:
    def __init__(self, *, put_response: dict[str, str] | None = None) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}
        self.puts: list[dict[str, object]] = []
        self.list_requests: list[dict[str, object]] = []
        self.put_response = {"ETag": '"committed-etag"'} if put_response is None else put_response

    def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
        self.list_requests.append(dict(kwargs))
        return {"Contents": [{"Key": "raw/events.json"}, {"Key": "raw/readme.txt"}]}

    def get_object(self, **kwargs: object) -> dict[str, object]:
        saved = self.objects.get((str(kwargs["Bucket"]), str(kwargs["Key"])))
        body = saved["Body"] if saved else b'[{"id": 1}]'
        if not isinstance(body, bytes):
            raise TypeError("stored fake S3 body must be bytes")
        return {"Body": _Body(body)}

    def put_object(self, **kwargs: object) -> dict[str, str]:
        self.puts.append(dict(kwargs))
        self.objects[(str(kwargs["Bucket"]), str(kwargs["Key"]))] = dict(kwargs)
        return self.put_response


def _connection() -> ConnectionDefinition:
    return ConnectionDefinition(
        ConnectionId("s3"), "S3", "s3.json", options=(("bucket", "data"), ("prefix", "raw"))
    )


def test_s3_json_discovers_and_snapshot_reads() -> None:
    connector = S3JsonConnector(client=_S3())
    connection = _connection()
    assets = connector.discover(connection, EnvironmentSecretResolver({}))
    assert [asset.handle.name for asset in assets] == ["events.json"]
    result = connector.read(connection, assets[0].handle, EnvironmentSecretResolver({}))
    unchanged = connector.read(
        connection, assets[0].handle, EnvironmentSecretResolver({}), checkpoint=result.checkpoint
    )
    assert result.rows == ({"id": 1},)
    assert unchanged.rows == ()


def test_s3_json_discovery_obeys_provider_page_limit() -> None:
    client = _S3()
    connector = S3JsonConnector(client=client)
    connection = _connection()
    resolver = EnvironmentSecretResolver({})

    assert connector.descriptor.capabilities.max_page_size == 1000
    with pytest.raises(ValueError, match="between 1 and 1000"):
        connector.discover_page(connection, resolver, page_size=1001)
    assert client.list_requests == []

    connector.discover_page(connection, resolver, page_size=1000)
    assert client.list_requests[0]["MaxKeys"] == 1000


def test_s3_json_legacy_discover_stops_after_bounded_provider_requests() -> None:
    class _EndlessS3(_S3):
        def list_objects_v2(self, **kwargs: object) -> dict[str, object]:
            self.list_requests.append(dict(kwargs))
            prior = kwargs.get("ContinuationToken")
            next_token = str(int(prior or "0") + 1)
            return {"Contents": [], "IsTruncated": True, "NextContinuationToken": next_token}

    client = _EndlessS3()
    connector = S3JsonConnector(client=client)
    with pytest.raises(ValueError, match="provider request limit"):
        connector.discover(_connection(), EnvironmentSecretResolver({}))
    assert len(client.list_requests) == connector.MAX_DISCOVERY_PAGES


def test_s3_json_rejects_unsafe_prefix_and_checkpoint() -> None:
    with pytest.raises(ValueError, match="unsafe"):
        S3JsonConnector(client=_S3()).discover(
            ConnectionDefinition(
                ConnectionId("s3"),
                "S3",
                "s3.json",
                options=(("bucket", "data"), ("prefix", "../raw")),
            ),
            EnvironmentSecretResolver({}),
        )
    with pytest.raises(ValueError, match="snapshot"):
        S3JsonConnector(client=_S3()).read(
            _connection(),
            AssetHandle(ConnectionId("s3"), ("raw",), "events.json"),
            EnvironmentSecretResolver({}),
            checkpoint=SourceCheckpoint("cursor", "x"),
        )


def test_s3_json_sink_writes_bounded_at_least_once_and_round_trips() -> None:
    client = _S3()
    connector = S3JsonConnector(client=client)
    connection = _connection()
    asset = AssetHandle(connection.id, ("raw",), "out.json")
    result = ConnectorReadResult(
        (FieldSchema("id", "integer"), FieldSchema("name", "string")),
        ({"id": 1, "name": "ronin"}, {"id": 2, "name": "dog"}),
    )
    registry = ConnectorRegistry((connector,))
    receipt = registry.write(
        "s3.json",
        connection,
        asset,
        result,
        EnvironmentSecretResolver({}),
        idempotency_key="sync-42",
    )

    payload = b'[{"id":1,"name":"ronin"},{"id":2,"name":"dog"}]'
    assert receipt.transactional is False
    assert receipt.idempotency_enforced is False
    assert receipt.delivery_semantics == "at_least_once"
    assert receipt.idempotency_key == "sync-42"
    assert receipt.commit_id == "committed-etag"
    assert receipt.output_id == "s3://data/raw/out.json"
    assert receipt.output_digest == hashlib.sha256(payload).hexdigest()
    assert client.puts[0]["Body"] == payload
    assert client.puts[0]["ContentType"] == "application/json"
    metadata = cast(dict[str, str], client.puts[0]["Metadata"])
    assert metadata["ronin-output-sha256"] == receipt.output_digest
    assert metadata["ronin-idempotency-key-sha256"] == hashlib.sha256(b"sync-42").hexdigest()
    assert connector.read(connection, asset, EnvironmentSecretResolver({})).rows == result.rows


def test_s3_jsonl_sink_and_empty_json_payload_are_valid() -> None:
    client = _S3()
    connector = S3JsonConnector(client=client)
    connection = _connection()
    resolver = EnvironmentSecretResolver({})

    receipt = connector.write(
        connection,
        AssetHandle(connection.id, ("raw",), "events.jsonl"),
        ConnectorReadResult((FieldSchema("id", "integer"),), ({"id": 1}, {"id": 2})),
        resolver,
        idempotency_key="jsonl-1",
    )
    assert client.puts[0]["Body"] == b'{"id":1}\n{"id":2}\n'
    assert client.puts[0]["ContentType"] == "application/x-ndjson"
    assert receipt.delivery_semantics == "at_least_once"

    connector.write(
        connection,
        AssetHandle(connection.id, ("raw",), "empty.json"),
        ConnectorReadResult((), ()),
        resolver,
        idempotency_key="empty-1",
    )
    assert client.puts[1]["Body"] == b"[]"


def test_s3_json_sink_reports_at_least_once_for_changed_payload_reusing_key() -> None:
    client = _S3()
    connector = S3JsonConnector(client=client)
    connection = _connection()
    asset = AssetHandle(connection.id, ("raw",), "mutable.json")
    resolver = EnvironmentSecretResolver({})
    fields = (FieldSchema("id", "integer"),)

    first = connector.write(
        connection,
        asset,
        ConnectorReadResult(fields, ({"id": 1},)),
        resolver,
        idempotency_key="same-operation-key",
    )
    second = connector.write(
        connection,
        asset,
        ConnectorReadResult(fields, ({"id": 2},)),
        resolver,
        idempotency_key="same-operation-key",
    )

    metadata = [cast(dict[str, str], put["Metadata"]) for put in client.puts]
    assert first.output_digest != second.output_digest
    assert (
        metadata[0]["ronin-idempotency-key-sha256"] == metadata[1]["ronin-idempotency-key-sha256"]
    )
    assert first.idempotency_enforced is second.idempotency_enforced is False
    assert client.objects[("data", "raw/mutable.json")]["Body"] == b'[{"id":2}]'


@pytest.mark.parametrize(
    "put_response",
    [{}, {"VersionId": "bad\nversion"}, {"ETag": " "}, {"ETag": "x" * 1025}],
)
def test_s3_json_sink_uses_digest_as_commit_id_when_provider_receipt_is_invalid(
    put_response: dict[str, str],
) -> None:
    connector = S3JsonConnector(client=_S3(put_response=put_response))
    connection = _connection()
    receipt = connector.write(
        connection,
        AssetHandle(connection.id, ("raw",), "output.json"),
        ConnectorReadResult((FieldSchema("id", "integer"),), ({"id": 9},)),
        EnvironmentSecretResolver({}),
        idempotency_key="no-version-1",
    )

    assert receipt.commit_id == f"sha256:{receipt.output_digest}"


def test_s3_json_sink_fails_closed_for_bad_targets_and_transactional_writes() -> None:
    client = _S3()
    connector = S3JsonConnector(client=client)
    connection = _connection()
    registry = ConnectorRegistry((connector,))
    result = ConnectorReadResult((), ())
    resolver = EnvironmentSecretResolver({})

    with pytest.raises(ConnectorCapabilityError, match="does not advertise transactional"):
        registry.write(
            "s3.json",
            connection,
            AssetHandle(connection.id, ("raw",), "out.json"),
            result,
            resolver,
            idempotency_key="write-1",
            transactional=True,
        )
    for asset, message in (
        (AssetHandle(connection.id, ("other",), "out.json"), "outside the configured prefix"),
        (AssetHandle(connection.id, ("raw",), "out.csv"), "only supports"),
        (AssetHandle(connection.id, ("raw", ".."), "out.json"), "unsafe component"),
    ):
        with pytest.raises(ValueError, match=message):
            connector.write(connection, asset, result, resolver, idempotency_key="write-1")
    with pytest.raises(ValueError, match="finite JSON"):
        connector.write(
            connection,
            AssetHandle(connection.id, ("raw",), "nan.json"),
            ConnectorReadResult((FieldSchema("value", "number"),), ({"value": float("nan")},)),
            resolver,
            idempotency_key="write-1",
        )
    assert client.puts == []


def test_s3_json_sink_enforces_row_and_byte_limits_before_put() -> None:
    client = _S3()
    connector = S3JsonConnector(client=client)
    connection = _connection()
    resolver = EnvironmentSecretResolver({})
    asset = AssetHandle(connection.id, ("raw",), "out.json")

    too_many_rows = ConnectorReadResult(
        (FieldSchema("id", "integer"),),
        tuple({"id": index} for index in range(S3JsonConnector.MAX_BATCH_SIZE + 1)),
    )
    with pytest.raises(ValueError, match="row limit"):
        connector.write(connection, asset, too_many_rows, resolver, idempotency_key="limit-1")

    too_many_bytes = ConnectorReadResult(
        (FieldSchema("payload", "string"),),
        ({"payload": "x" * (S3JsonConnector.MAX_OBJECT_BYTES + 1)},),
    )
    with pytest.raises(ValueError, match="byte limit"):
        connector.write(connection, asset, too_many_bytes, resolver, idempotency_key="limit-2")
    assert client.puts == []


def test_s3_json_sink_rejects_unrepresentable_receipt_and_utf8_before_put() -> None:
    client = _S3()
    connector = S3JsonConnector(client=client)
    connection = _connection()
    resolver = EnvironmentSecretResolver({})
    result = ConnectorReadResult((), ())

    oversized_output = AssetHandle(connection.id, ("raw",), f"{'x' * 1015}.json")
    with pytest.raises(ValueError, match="receipt limit"):
        connector.write(connection, oversized_output, result, resolver, idempotency_key="receipt-1")

    invalid_utf8_path = AssetHandle(connection.id, ("raw",), "bad\ud800.json")
    with pytest.raises(ValueError, match="valid UTF-8"):
        connector.write(
            connection, invalid_utf8_path, result, resolver, idempotency_key="utf8-path-1"
        )

    with pytest.raises(ValueError, match="valid UTF-8"):
        connector.write(
            connection,
            AssetHandle(connection.id, ("raw",), "valid.json"),
            result,
            resolver,
            idempotency_key="bad\ud800",
        )

    invalid_bucket_receipt = ConnectionDefinition(
        connection.id,
        "Invalid bucket",
        "s3.json",
        options=(("bucket", "bad\tbucket"), ("prefix", "raw")),
    )
    with pytest.raises(ValueError, match="control characters"):
        connector.write(
            invalid_bucket_receipt,
            AssetHandle(invalid_bucket_receipt.id, ("raw",), "output.json"),
            result,
            resolver,
            idempotency_key="invalid-bucket-1",
        )

    assert client.puts == []
