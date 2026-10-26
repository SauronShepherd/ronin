import base64
from contextlib import contextmanager
from threading import Event

import pytest
from studio_connectors import (
    ConnectorRegistry,
    IngestionHTTPAdapter,
    IngestionSyncCancelled,
    IngestionSyncDefinition,
    IngestionSyncPlan,
    IngestionSyncService,
    SqliteConnectorCheckpointStore,
    plan_sync,
)
from studio_connectors.contracts import ConnectorReadResult, DiscoveryPage
from studio_core import (
    AssetHandle,
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    ConnectionId,
    ConnectorCapabilities,
    ConnectorDescriptor,
    DiscoveredAsset,
    FieldSchema,
    SourceCheckpoint,
    Workspace,
    WorkspaceId,
)
from studio_core.canonical_json import decode, encode
from studio_orchestrator import Instant
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore


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
        self.discover_page_calls = 0
        self.descriptor = ConnectorDescriptor(
            "paged-db",
            1,
            ConnectorCapabilities(discover=True, max_page_size=2),
        )

    def discover_page(self, connection, secrets, *, cursor=None, page_size=1000):
        del secrets
        self.discover_page_calls += 1
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
    governed = IngestionSyncDefinition(
        "sync/governed",
        "postgres",
        "conn/main",
        "table/customers",
        "artifact/customers",
        "project/customers",
        source_revision_ref=AssetRef(AssetId("source"), AssetVersion("v1")),
        destination_asset_id=AssetId("target"),
    )
    assert IngestionSyncDefinition.from_bytes(governed.to_bytes()) == governed


def test_governed_sync_commits_destination_revision_lineage_and_checkpoint(tmp_path) -> None:
    now = Instant("2026-10-25T12:00:00.000000Z")
    workspace = WorkspaceId("workspace-sync")
    path = tmp_path / "shared.sqlite3"
    SqliteWorkspaceStore(path, migration_now=now).create_workspace(
        Workspace(workspace, "Sync workspace"), now=now
    )
    catalog = SqliteCatalogStore(path, migration_now=now)
    source_id, target_id = AssetId("source"), AssetId("target")
    source_ref = AssetRef(source_id, AssetVersion("source-v1"))
    catalog.create_asset(
        workspace,
        CatalogAsset(
            source_id,
            "table",
            "Source",
            properties=(
                ("ronin.connector_id", "connector"),
                ("ronin.connection_ref", "connection"),
                ("ronin.asset_ref", "asset"),
            ),
        ),
        now=str(now),
    )
    catalog.create_asset(workspace, CatalogAsset(target_id, "table", "Target"), now=now)
    catalog.put_revision(workspace, AssetRevision(source_ref), now=now)

    class Registry:
        def plan_sync(self, _definition, *, checkpoint_present):
            assert checkpoint_present is False
            return IngestionSyncPlan("sync", "connector", "snapshot", "checkpoint", False)

        def read(self, *_args, **_kwargs):
            return ConnectorReadResult(
                (FieldSchema("id", "integer", False),),
                ({"id": 1},),
                SourceCheckpoint("snapshot", "next"),
            )

    class Destination:
        def write(self, *_args, **_kwargs):
            return "artifact:sync-output", "a" * 64

    destination_id = target_id
    definition = IngestionSyncDefinition(
        "sync/governed",
        "connector",
        "connection",
        "asset",
        "destination",
        "checkpoint",
        source_revision_ref=source_ref,
        destination_asset_id=destination_id,
    )
    checkpoints = SqliteConnectorCheckpointStore(path)
    result = IngestionSyncService(Registry(), checkpoints).execute(
        definition,
        workspace_id=str(workspace),
        connection=object(),
        asset=object(),
        secrets=object(),
        destination=Destination(),
        execution_ref="run/durable-1",
        now=str(now),
    )
    target_ref = AssetRef(target_id, AssetVersion("sha256:" + "a" * 64))
    edges = catalog.upstream(workspace, target_ref)
    assert result["lineage"] == edges[0].to_payload()
    assert edges[0].execution_ref == "run/durable-1"
    assert catalog.get_revision(workspace, target_ref) is not None
    assert checkpoints.get("workspace-sync/checkpoint") == SourceCheckpoint("snapshot", "next")


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


def test_ingestion_sync_commits_bounded_batches_and_resumes_after_page_budget() -> None:
    from hashlib import sha256
    from types import SimpleNamespace

    class Registry:
        read_positions: list[int] = []

        def plan_sync(self, definition, *, checkpoint_present):
            return plan_sync(
                definition, incremental_capable=True, checkpoint_present=checkpoint_present
            )

        def read(self, _connector, _connection, _asset, _secrets, *, checkpoint, limit):
            assert limit == 1
            position = 0 if checkpoint is None else int(checkpoint.value)
            self.read_positions.append(position)
            next_position = position + 1
            return ConnectorReadResult(
                (FieldSchema("id", "integer", False),),
                ({"id": next_position},),
                SourceCheckpoint("watermark", str(next_position)),
                has_more=next_position < 4,
            )

    class Checkpoints:
        current = None

        def health(self, _identity):
            return SimpleNamespace(present=self.current is not None)

        def get(self, _identity):
            return self.current

        def acquire(self, _identity):
            return 1

        def commit_output_then_checkpoint(self, _identity, expected, next_checkpoint, **_kwargs):
            assert self.current == expected
            self.current = next_checkpoint

            class Evidence:
                def to_payload(self):
                    return {"identity": "workspace/checkpoint", "digest": next_checkpoint.digest}

            return Evidence()

    class Destination:
        outputs: list[int] = []

        def write(self, _destination_ref, result, *, fence):
            assert fence == 1
            row_id = result.rows[0]["id"]
            self.outputs.append(row_id)
            return f"artifact-{row_id}", sha256(str(row_id).encode()).hexdigest()

    registry = Registry()
    checkpoints = Checkpoints()
    destination = Destination()
    service = IngestionSyncService(registry, checkpoints, max_batches=2)
    definition = IngestionSyncDefinition(
        "sync-pages", "connector", "connection", "asset", "destination", "checkpoint"
    )

    first = service.execute(
        definition,
        workspace_id="workspace",
        connection=object(),
        asset=object(),
        secrets=object(),
        destination=destination,
        limit=1,
    )
    assert first["rows_written"] == 2
    assert first["batches"] == 2
    assert first["has_more"] is True
    assert checkpoints.current == SourceCheckpoint("watermark", "2")

    second = service.execute(
        definition,
        workspace_id="workspace",
        connection=object(),
        asset=object(),
        secrets=object(),
        destination=destination,
        limit=1,
    )
    assert second["rows_written"] == 2
    assert second["batches"] == 2
    assert second["has_more"] is False
    assert checkpoints.current == SourceCheckpoint("watermark", "4")
    assert registry.read_positions == [0, 1, 2, 3]
    assert destination.outputs == [1, 2, 3, 4]


def test_ingestion_sync_rejects_unbounded_or_invalid_batch_configuration() -> None:
    with pytest.raises(ValueError, match="max_batches"):
        IngestionSyncService(object(), object(), max_batches=True)
    with pytest.raises(ValueError, match="limit"):
        IngestionSyncService(object(), object()).execute(
            IngestionSyncDefinition("sync", "connector", "connection", "asset", "dest", "cp"),
            workspace_id="workspace",
            connection=object(),
            asset=object(),
            secrets=object(),
            destination=object(),
            limit=0,
        )


def test_connector_json_projection_preserves_database_scalar_precision() -> None:
    from datetime import UTC, date, datetime
    from decimal import Decimal
    from uuid import UUID

    from studio_connectors.json_compatible import json_compatible

    assert json_compatible(
        {
            "id": 2**62,
            "amount": Decimal("12345678901234567890.1234567890"),
            "observed_at": datetime(2026, 1, 2, tzinfo=UTC),
            "day": date(2026, 1, 2),
            "uuid": UUID(int=1),
            "raw": b"data",
        }
    ) == {
        "id": str(2**62),
        "amount": "12345678901234567890.1234567890",
        "observed_at": "2026-01-02T00:00:00+00:00",
        "day": "2026-01-02",
        "uuid": "00000000-0000-0000-0000-000000000001",
        "raw": "ZGF0YQ",
    }
    with pytest.raises(ValueError, match="non-finite"):
        json_compatible(float("nan"))
    nested = 1
    for _ in range(66):
        nested = [nested]
    with pytest.raises(ValueError, match="nesting depth"):
        json_compatible(nested)


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
        cursor_signing_key=b"t" * 32,
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
        cursor_signing_key=b"t" * 32,
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
        cursor_signing_key=b"t" * 32,
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


def test_discovery_rejects_foreign_cursor_before_secret_resolution_or_provider_io() -> None:
    connector = _PagedDiscoveringConnector()
    secret_resolutions: list[str] = []
    adapter = IngestionHTTPAdapter(
        ConnectorRegistry((connector,)),
        object(),
        lambda _workspace, _ref: type(
            "Connection", (), {"id": "conn/a", "connector_id": "paged-db"}
        )(),
        lambda ref: ref,
        lambda ref: secret_resolutions.append(ref) or ref,
        cursor_signing_key=b"t" * 32,
    )
    request = {"connector_id": "paged-db", "connection_ref": "conn/a", "page_size": 2}
    first = adapter.discover(request, workspace_id="workspace/a")
    assert secret_resolutions == ["conn/a"]
    calls_before = connector.discover_page_calls
    cursor = first["next_cursor"]
    assert isinstance(cursor, str)

    raw_cursor = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
    payload = decode(raw_cursor[:-32])
    payload["provider_cursor"] = "999"
    tampered_cursor = (
        base64.urlsafe_b64encode(encode(payload) + raw_cursor[-32:]).decode("ascii").rstrip("=")
    )
    with pytest.raises(ValueError, match="signature is invalid"):
        adapter.discover({**request, "cursor": tampered_cursor}, workspace_id="workspace/a")
    assert secret_resolutions == ["conn/a"]
    assert connector.discover_page_calls == calls_before

    with pytest.raises(ValueError, match="different source scope"):
        adapter.discover(
            {**request, "cursor": cursor},
            workspace_id="workspace/b",
        )

    assert secret_resolutions == ["conn/a"]
    assert connector.discover_page_calls == calls_before


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
        cursor_signing_key=b"t" * 32,
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
        cursor_signing_key=b"t" * 32,
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


@pytest.mark.parametrize("cancel_stage", ["before_read", "after_read", "during_write"])
def test_sync_cancellation_does_not_advance_checkpoint(tmp_path, cancel_stage: str) -> None:
    cancellation = Event()
    if cancel_stage == "before_read":
        cancellation.set()
    commits: list[str] = []
    writes: list[str] = []
    reads: list[str] = []
    acquires: list[str] = []

    class _Registry:
        def plan_sync(self, definition, *, checkpoint_present):
            assert checkpoint_present is False
            return IngestionSyncPlan(
                definition.id,
                definition.connector_id,
                definition.mode,
                definition.checkpoint_identity,
                False,
            )

        def read(self, *_args, **_kwargs):
            reads.append("read")
            if cancel_stage == "after_read":
                cancellation.set()
            return ConnectorReadResult((), (), SourceCheckpoint("snapshot", "next"))

    class _Checkpoints(SqliteConnectorCheckpointStore):
        def acquire(self, identity):
            acquires.append(identity)
            return super().acquire(identity)

        def commit_output_then_checkpoint(self, *args, **kwargs):
            commits.append("checkpoint")
            return super().commit_output_then_checkpoint(*args, **kwargs)

    class _Destination:
        def write(self, *_args, **_kwargs):
            writes.append("output")
            if cancel_stage == "during_write":
                cancellation.set()
            return "artifact-id", "a" * 64

    checkpoints = _Checkpoints(tmp_path / "checkpoints.sqlite")
    service = IngestionSyncService(_Registry(), checkpoints)

    with pytest.raises(IngestionSyncCancelled, match="cancellation was requested"):
        service.execute(
            IngestionSyncDefinition("sync/a", "connector", "conn/a", "asset/a", "dest/a", "cp/a"),
            workspace_id="workspace/a",
            connection=object(),
            asset=object(),
            secrets=object(),
            destination=_Destination(),
            cancellation_requested=cancellation.is_set,
        )

    identity = IngestionHTTPAdapter._checkpoint_identity("workspace/a", "cp/a")
    assert checkpoints.get(identity) is None
    assert checkpoints.health(identity).output_committed is False
    assert reads == ([] if cancel_stage == "before_read" else ["read"])
    assert acquires == ([] if cancel_stage == "before_read" else [identity])
    assert writes == ([] if cancel_stage != "during_write" else ["output"])
    assert commits == []


@pytest.mark.parametrize(
    ("workspace_id", "identity"), [("", "cp"), ("workspace", " "), (" ws", "cp")]
)
def test_checkpoint_scope_encoding_rejects_untrimmed_components(
    workspace_id: str, identity: str
) -> None:
    with pytest.raises(ValueError, match="non-empty and trimmed"):
        IngestionHTTPAdapter._checkpoint_identity(workspace_id, identity)
