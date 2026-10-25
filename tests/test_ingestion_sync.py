from contextlib import contextmanager

import pytest
from studio_connectors import (
    ConnectorRegistry,
    IngestionHTTPAdapter,
    IngestionSyncDefinition,
    IngestionSyncService,
    SqliteConnectorCheckpointStore,
    plan_sync,
)
from studio_connectors.contracts import ConnectorReadResult, DiscoveryPage
from studio_core import (
    AssetHandle,
    ConnectionId,
    ConnectorCapabilities,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SourceCheckpoint,
)


class _Connector:
    def __init__(self, connector_id: str, incremental: bool) -> None:
        self.descriptor = ConnectorDescriptor(
            connector_id, 1, ConnectorCapabilities(read=True, incremental=incremental)
        )


class _DiscoveringConnector(_Connector):
    def __init__(self, connector_id: str, incremental: bool) -> None:
        super().__init__(connector_id, incremental)
        self.descriptor = ConnectorDescriptor(
            connector_id,
            1,
            ConnectorCapabilities(discover=True, max_page_size=100),
        )

    def discover(self, connection, secrets):
        del secrets
        return (
            DiscoveredAsset(
                AssetHandle(ConnectionId(connection.id), ("public",), "orders"),
                "table",
                (FieldSchema("id", "integer", False),),
            ),
        )

    def discover_page(self, connection, secrets, *, cursor=None, page_size=1000):
        del cursor
        assets = self.discover(connection, secrets)
        return DiscoveryPage(assets[:page_size], None, False)


class _PagedDiscoveringConnector(_DiscoveringConnector):
    def __init__(self) -> None:
        self.descriptor = ConnectorDescriptor(
            "paged-db",
            1,
            ConnectorCapabilities(discover=True, max_page_size=2),
        )

    def discover_page(self, connection, secrets, *, cursor=None, page_size=1000):
        del secrets
        all_assets = tuple(
            DiscoveredAsset(
                AssetHandle(ConnectionId(connection.id), (), name),
                "table",
                (),
            )
            for name in ("orders", "products", "users")
        )
        offset = int(cursor or "0")
        selected = all_assets[offset : offset + page_size]
        next_offset = offset + len(selected)
        truncated = next_offset < len(all_assets)
        return DiscoveryPage(selected, str(next_offset) if truncated else None, truncated)


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


def test_incremental_plan_rejects_checkpoint_fence_without_durable_output(tmp_path) -> None:
    registry = ConnectorRegistry((_Connector("postgres", True),))
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoints.sqlite")
    identity = "project/source/table"
    store.acquire(identity)
    definition = IngestionSyncDefinition(
        "sync/a", "postgres", "conn/a", "asset/a", "artifact/a", identity, "incremental"
    )

    with pytest.raises(ValueError, match="existing checkpoint"):
        registry.plan_sync(definition, checkpoint_present=store.health(identity).present)


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
        lambda workspace, ref: ("connection", workspace, ref),
        lambda ref: ("asset", ref),
        lambda ref: ("secrets", ref),
    )

    class _Service:
        def preview(self, definition, *, workspace_id, connection, asset, secrets):
            return {
                "schema": "ronin.ingestion-preview/v1",
                "definition_id": definition.id,
                "resolved": [connection[1:], asset[1], secrets[1]],
                "workspace_id": workspace_id,
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
    assert adapter.preview(body, workspace_id="workspace/a")["resolved"] == [
        ("workspace/a", "conn/a"),
        "asset/a",
        "conn/a",
    ]
    assert adapter.preview(body, workspace_id="workspace/a")["workspace_id"] == "workspace/a"
    with pytest.raises(ValueError, match="invalid fields"):
        adapter.preview({**body, "extra": True}, workspace_id="workspace/a")


def test_ingestion_http_adapter_discovers_bounded_assets() -> None:
    registry = ConnectorRegistry((_DiscoveringConnector("postgres", False),))
    workspaces: list[str] = []
    adapter = IngestionHTTPAdapter(
        registry,
        object(),
        lambda workspace, _ref: (
            workspaces.append(workspace)
            or type("Connection", (), {"id": "conn/a", "connector_id": "postgres"})()
        ),
        lambda ref: ref,
        lambda ref: ref,
    )

    result = adapter.discover(
        {"connector_id": "postgres", "connection_ref": "conn/a"},
        workspace_id="workspace/a",
    )

    assert result["schema"] == "ronin.connector-discovery/v1"
    assert workspaces == ["workspace/a"]
    assert result["count"] == 1
    assert result["has_more"] is False
    assert result["next_cursor"] is None
    assert result["items"] == [
        {
            "asset_ref": "conn/a::public.orders",
            "kind": "table",
            "fields": [{"name": "id", "data_type": "integer", "nullable": False}],
        }
    ]


def test_ingestion_http_adapter_pages_discovery_and_scopes_cursor() -> None:
    connector = _PagedDiscoveringConnector()
    adapter = IngestionHTTPAdapter(
        ConnectorRegistry((connector,)),
        object(),
        lambda _workspace, _ref: type(
            "Connection", (), {"id": "conn/a", "connector_id": "paged-db"}
        )(),
        lambda ref: ref,
        lambda ref: ref,
    )
    request = {"connector_id": "paged-db", "connection_ref": "conn/a", "page_size": 2}

    first = adapter.discover(request, workspace_id="workspace/a")

    assert first["count"] == 2
    assert first["has_more"] is True
    assert first["items"][0]["asset_ref"] == "conn/a::orders"
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)
    second = adapter.discover({**request, "cursor": cursor}, workspace_id="workspace/a")
    assert second["count"] == 1
    assert second["has_more"] is False
    assert second["next_cursor"] is None
    assert second["items"][0]["asset_ref"] == "conn/a::users"

    with pytest.raises(ValueError, match="different source scope"):
        adapter.discover({**request, "cursor": cursor}, workspace_id="workspace/b")
    with pytest.raises(ValueError, match="different source scope"):
        adapter.discover(
            {**request, "connection_ref": "conn/other", "cursor": cursor},
            workspace_id="workspace/a",
        )

    with pytest.raises(ValueError, match="advertised limit"):
        adapter.discover(
            {**request, "page_size": 3},
            workspace_id="workspace/a",
        )

    with pytest.raises(ValueError, match="must be an integer"):
        adapter.discover(
            {**request, "page_size": True},
            workspace_id="workspace/a",
        )


def test_ingestion_http_adapter_rejects_non_advancing_discovery_cursor() -> None:
    class _RepeatingConnector(_PagedDiscoveringConnector):
        def discover_page(self, connection, secrets, *, cursor=None, page_size=1000):
            del connection, secrets, page_size
            return DiscoveryPage((), cursor or "same", True)

    adapter = IngestionHTTPAdapter(
        ConnectorRegistry((_RepeatingConnector(),)),
        object(),
        lambda _workspace, _ref: type(
            "Connection", (), {"id": "conn/a", "connector_id": "paged-db"}
        )(),
        lambda ref: ref,
        lambda ref: ref,
    )
    first = adapter.discover(
        {"connector_id": "paged-db", "connection_ref": "conn/a"},
        workspace_id="workspace/a",
    )

    with pytest.raises(ValueError, match="did not advance"):
        adapter.discover(
            {
                "connector_id": "paged-db",
                "connection_ref": "conn/a",
                "cursor": first["next_cursor"],
            },
            workspace_id="workspace/a",
        )


def test_discovery_page_requires_cursor_when_truncated() -> None:
    with pytest.raises(ValueError, match="must provide a continuation cursor"):
        DiscoveryPage((), None, True)


def test_ingestion_http_adapter_scopes_checkpoint_health_by_workspace() -> None:
    identities: list[str] = []

    class _Health:
        present = False

        def to_payload(self) -> dict[str, object]:
            return {"schema": "ronin.connector-checkpoint-health/v1", "present": False}

    class _Checkpoints:
        def health(self, identity: str) -> _Health:
            identities.append(identity)
            return _Health()

    adapter = IngestionHTTPAdapter(
        ConnectorRegistry((_Connector("postgres", False),)),
        _Checkpoints(),
        lambda _workspace, _ref: None,
        lambda ref: ref,
        lambda ref: ref,
    )
    body = {
        "id": "sync/a",
        "connector_id": "postgres",
        "connection_ref": "conn/a",
        "asset_ref": "asset/a",
        "destination_ref": "artifact/a",
        "checkpoint_identity": "cp/a",
        "mode": "snapshot",
    }

    result = adapter.plan(body, workspace_id="workspace/a")
    health = adapter.checkpoint_health({"checkpoint_identity": "cp/a"}, workspace_id="workspace/b")

    assert len(identities) == 2
    assert identities[0].startswith("ronin:v2:")
    assert identities[1].startswith("ronin:v2:")
    assert identities[0] != identities[1]
    assert result["checkpoint"]["identity"] == "cp/a"
    assert health["identity"] == "cp/a"


def test_ingestion_preview_scopes_checkpoint_read_and_hides_internal_identity() -> None:
    identities: list[str] = []

    class _Health:
        present = False

        def to_payload(self) -> dict[str, object]:
            return {"schema": "ronin.connector-checkpoint-health/v1", "identity": "internal"}

    class _Checkpoints:
        def health(self, identity: str) -> _Health:
            identities.append(identity)
            return _Health()

    class _Plan:
        digest = "a" * 64

        def to_payload(self) -> dict[str, object]:
            return {"checkpoint_identity": "cp/a"}

    class _Registry:
        def plan_sync(self, _definition, *, checkpoint_present: bool) -> _Plan:
            assert checkpoint_present is False
            return _Plan()

        def preview(self, *_args, **_kwargs) -> ConnectorReadResult:
            return ConnectorReadResult((), ())

    definition = IngestionSyncDefinition(
        "sync/a", "postgres", "conn/a", "asset/a", "artifact/a", "cp/a", "snapshot"
    )
    result = IngestionSyncService(_Registry(), _Checkpoints()).preview(
        definition,
        workspace_id="workspace/a",
        connection=object(),
        asset=object(),
        secrets=object(),
    )

    assert identities == [IngestionHTTPAdapter._checkpoint_identity("workspace/a", "cp/a")]
    assert result["checkpoint"]["identity"] == "cp/a"


def test_checkpoint_scope_encoding_cannot_alias_slash_delimited_pairs() -> None:
    identity = IngestionHTTPAdapter._checkpoint_identity

    assert identity("workspace", "checkpoint") == "workspace/checkpoint"
    assert identity("workspace/a", "b/c") != identity("workspace/a/b", "c")


def test_sync_holds_reference_barrier_through_artifact_and_checkpoint_commit() -> None:
    events: list[str] = []
    identities: list[str] = []

    class _Barrier:
        @contextmanager
        def writer(self):
            events.append("lock")
            try:
                yield
            finally:
                events.append("unlock")

        @contextmanager
        def collector(self):
            yield

    class _Health:
        present = False

    class _Plan:
        digest = "plan-digest"

        def to_payload(self):
            return {"digest": self.digest}

    class _Registry:
        def plan_sync(self, _definition, *, checkpoint_present):
            assert checkpoint_present is False
            return _Plan()

        def read(self, *_args, **_kwargs):
            return ConnectorReadResult((), (), SourceCheckpoint("snapshot", "next"))

    class _Checkpoints:
        def health(self, identity):
            identities.append(identity)
            return _Health()

        def get(self, identity):
            identities.append(identity)

        def acquire(self, identity):
            identities.append(identity)
            return 1

        def commit_output_then_checkpoint(self, identity, *_args, **_kwargs):
            identities.append(identity)
            events.append("reference")

            class _Evidence:
                def to_payload(self):
                    return {"committed": True, "identity": identity}

            return _Evidence()

    class _Destination:
        def write(self, *_args, **_kwargs):
            events.append("artifact")
            return "artifact-id", "artifact-digest"

    service = IngestionSyncService(
        _Registry(),
        _Checkpoints(),
        artifact_reference_barrier=_Barrier(),
    )
    result = service.execute(
        IngestionSyncDefinition("sync/a", "connector", "conn/a", "asset/a", "dest/a", "cp/a"),
        workspace_id="workspace/a",
        connection=object(),
        asset=object(),
        secrets=object(),
        destination=_Destination(),
    )

    assert result["rows_written"] == 0
    assert result["checkpoint"]["identity"] == "cp/a"
    assert events == ["lock", "artifact", "reference", "unlock"]
    assert identities == [IngestionHTTPAdapter._checkpoint_identity("workspace/a", "cp/a")] * 4


@pytest.mark.parametrize(
    ("workspace_id", "identity"), [("", "cp"), ("workspace", " "), (" ws", "cp")]
)
def test_checkpoint_scope_encoding_rejects_untrimmed_components(
    workspace_id: str, identity: str
) -> None:
    with pytest.raises(ValueError, match="non-empty and trimmed"):
        IngestionHTTPAdapter._checkpoint_identity(workspace_id, identity)
