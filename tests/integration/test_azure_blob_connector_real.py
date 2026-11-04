"""Azure Blob JSON connector qualification against a local Azurite service."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from studio_connectors import AzureBlobJsonConnector
from studio_core import AssetHandle, ConnectionDefinition, ConnectionId, SecretRef
from studio_storage import EnvironmentSecretResolver


def test_azure_blob_discovers_reads_and_replays_snapshot_against_azurite() -> None:
    endpoint = os.environ.get("RONIN_AZURITE_ENDPOINT")
    account_key = os.environ.get("RONIN_AZURITE_ACCOUNT_KEY")
    if not endpoint or not account_key:
        pytest.skip("RONIN_AZURITE_ENDPOINT and RONIN_AZURITE_ACCOUNT_KEY are required")
    from azure.storage.blob import BlobServiceClient

    account_name = os.environ.get("RONIN_AZURITE_ACCOUNT", "devstoreaccount1")
    account_url = f"{endpoint.rstrip('/')}/{account_name}"
    api_version = "2025-11-05"
    container_name = f"ronin-qual-{uuid4().hex}"
    service = BlobServiceClient(
        account_url=account_url,
        credential=account_key,
        api_version=api_version,
    )
    container = service.get_container_client(container_name)
    container.create_container()
    prefix = "raw"
    container.upload_blob(
        f"{prefix}/events.jsonl",
        b'{"id":1,"name":"Ada"}\n{"id":2,"name":"Grace"}\n',
    )
    container.upload_blob("ignored.txt", b"not a supported data object")
    connection = ConnectionDefinition(
        ConnectionId("azurite-live"),
        "Local Azure-compatible qualification",
        "azure.blob.json",
        options=(
            ("account_url", account_url),
            ("api_version", api_version),
            ("allow_local_http", "true"),
            ("container", container_name),
            ("prefix", prefix),
        ),
        secret_refs=(("credential", SecretRef("secret://env/RONIN_AZURITE_ACCOUNT_KEY")),),
    )
    secrets = EnvironmentSecretResolver({"RONIN_AZURITE_ACCOUNT_KEY": account_key})
    connector = AzureBlobJsonConnector()
    try:
        discovered = connector.discover(connection, secrets)
        assert len(discovered) == 1
        asset = discovered[0].handle
        assert asset == AssetHandle(connection.id, (prefix,), "events.jsonl")
        first = connector.read(connection, asset, secrets)
        replay = connector.read(connection, asset, secrets, checkpoint=first.checkpoint)

        assert first.rows == ({"id": 1, "name": "Ada"}, {"id": 2, "name": "Grace"})
        assert {field.name for field in first.fields} == {"id", "name"}
        assert first.checkpoint.strategy == "snapshot"
        assert first.checkpoint.value
        assert replay.rows == ()
        assert replay.checkpoint == first.checkpoint
        assert account_key not in repr(connection)
    finally:
        container.delete_container()
        service.close()
