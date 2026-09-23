import pytest
from studio_connectors import (
    ConnectorRegistry,
    IngestionHTTPAdapter,
    IngestionSyncDefinition,
    plan_sync,
)
from studio_core import ConnectorCapabilities, ConnectorDescriptor


class _Connector:
    def __init__(self, connector_id: str, incremental: bool) -> None:
        self.descriptor = ConnectorDescriptor(
            connector_id, 1, ConnectorCapabilities(read=True, incremental=incremental)
        )


def test_ingestion_sync_round_trips_canonically() -> None:
    definition = IngestionSyncDefinition(
        "sync/customers",
        "postgres",
        "conn/main",
        "table/customers",
        "artifact/customers",
        "project/customers",
        "incremental",
    )
    assert IngestionSyncDefinition.from_bytes(definition.to_bytes()) == definition


def test_ingestion_sync_rejects_invalid_mode() -> None:
    with pytest.raises(ValueError, match="snapshot or incremental"):
        IngestionSyncDefinition(
            "sync/a", "http", "conn/a", "asset/a", "artifact/a", "cp/a", "stream"
        )


def test_incremental_sync_plan_requires_capability_and_checkpoint() -> None:
    definition = IngestionSyncDefinition(
        "sync/a", "postgres", "conn/a", "asset/a", "artifact/a", "cp/a", "incremental"
    )
    with pytest.raises(ValueError, match="incremental capability"):
        plan_sync(definition, incremental_capable=False, checkpoint_present=False)
    with pytest.raises(ValueError, match="existing checkpoint"):
        plan_sync(definition, incremental_capable=True, checkpoint_present=False)
    assert plan_sync(
        definition, incremental_capable=True, checkpoint_present=True
    ).requires_checkpoint


def test_registry_derives_incremental_capability_from_descriptor() -> None:
    definition = IngestionSyncDefinition(
        "sync/a", "postgres", "conn/a", "asset/a", "artifact/a", "cp/a", "snapshot"
    )
    plan = ConnectorRegistry((_Connector("postgres", False),)).plan_sync(
        definition, checkpoint_present=False
    )
    assert plan.mode == "snapshot"
    assert len(plan.digest) == 64
    assert plan.to_payload()["digest"] == plan.digest


def test_ingestion_http_adapter_validates_and_delegates_preview() -> None:
    registry = ConnectorRegistry((_Connector("postgres", False),))
    adapter = IngestionHTTPAdapter(
        registry,
        object(),
        lambda ref: ("connection", ref),
        lambda ref: ("asset", ref),
        lambda ref: ("secrets", ref),
    )

    class _Service:
        def preview(self, definition, *, connection, asset, secrets):
            return {
                "schema": "ronin.ingestion-preview/v1",
                "definition_id": definition.id,
                "resolved": [connection[1], asset[1], secrets[1]],
            }

    adapter._service = _Service()
    body = {
        "id": "sync/a",
        "connector_id": "postgres",
        "connection_ref": "conn/a",
        "asset_ref": "asset/a",
        "destination_ref": "artifact/a",
        "checkpoint_identity": "cp/a",
        "mode": "snapshot",
    }
    assert adapter.preview(body)["resolved"] == ["conn/a", "asset/a", "conn/a"]
    with pytest.raises(ValueError, match="invalid fields"):
        adapter.preview({**body, "extra": True})
