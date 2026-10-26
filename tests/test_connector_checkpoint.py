from __future__ import annotations

from hashlib import sha256

import pytest
from studio_connectors import (
    CheckpointFenceConflict,
    SqliteConnectorCheckpointStore,
)
from studio_core import (
    AssetId,
    AssetRef,
    AssetRevision,
    AssetVersion,
    CatalogAsset,
    LineageEdge,
    SourceCheckpoint,
    Workspace,
    WorkspaceId,
)
from studio_orchestrator import Instant
from studio_storage import discover_connector_artifact_references
from studio_storage.catalog import SqliteCatalogStore
from studio_storage.workspaces import SqliteWorkspaceStore


def test_sqlite_discovery_cursor_signing_key_is_persistent_and_shared(tmp_path) -> None:
    path = tmp_path / "checkpoints.sqlite3"
    first_store = SqliteConnectorCheckpointStore(path)
    first_key = first_store.get_or_create_discovery_cursor_key()

    reopened_store = SqliteConnectorCheckpointStore(path)

    assert len(first_key) == 32
    assert reopened_store.get_or_create_discovery_cursor_key() == first_key


def test_checkpoint_catalog_lineage_and_destination_revision_commit_atomically(tmp_path) -> None:
    path = tmp_path / "shared.sqlite3"
    now = Instant("2026-10-25T12:00:00.000000Z")
    workspace = WorkspaceId("workspace-sync")
    source_id, target_id = AssetId("source"), AssetId("target")
    source_ref = AssetRef(source_id, AssetVersion("source-v1"))
    target_ref = AssetRef(target_id, AssetVersion("sha256:" + "a" * 64))
    SqliteWorkspaceStore(path, migration_now=now).create_workspace(
        Workspace(workspace, "Sync workspace"), now=now
    )
    catalog = SqliteCatalogStore(path, migration_now=now)
    catalog.create_asset(
        workspace,
        CatalogAsset(
            source_id,
            "table",
            "Source",
            properties=(
                ("ronin.connector_id", "postgres"),
                ("ronin.connection_ref", "connection-1"),
                ("ronin.asset_ref", "connection-1::table"),
            ),
        ),
        now=now,
    )
    catalog.create_asset(workspace, CatalogAsset(target_id, "table", "Target"), now=now)
    catalog.put_revision(workspace, AssetRevision(source_ref), now=now)
    edge = LineageEdge(
        source_ref, target_ref, operation="write", mode="observed", execution_ref="run-1"
    )
    checkpoints = SqliteConnectorCheckpointStore(path)
    identity = "workspace-sync/checkpoint"
    fence = checkpoints.acquire(identity)
    result = checkpoints.commit_output_then_checkpoint(
        identity,
        None,
        SourceCheckpoint("snapshot", "next"),
        output_id="artifact:sync-output",
        output_digest="a" * 64,
        fence=fence,
        output_committed=True,
        catalog_commit=(
            workspace,
            AssetRevision(target_ref, content_digest="a" * 64),
            edge,
            str(now),
            ("postgres", "connection-1", "connection-1::table"),
        ),
    )
    assert checkpoints.get(identity) == SourceCheckpoint("snapshot", "next")
    assert catalog.get_revision(workspace, target_ref) is not None
    assert catalog.upstream(workspace, target_ref) == (edge,)
    assert result.output_digest == "a" * 64


def test_checkpoint_catalog_failure_rolls_back_revision_lineage_and_checkpoint(tmp_path) -> None:
    path = tmp_path / "shared.sqlite3"
    now = Instant("2026-10-25T12:00:00.000000Z")
    workspace = WorkspaceId("workspace-sync")
    source_ref = AssetRef(AssetId("missing-source"), AssetVersion("v1"))
    target_ref = AssetRef(AssetId("target"), AssetVersion("sha256:" + "b" * 64))
    SqliteWorkspaceStore(path, migration_now=now).create_workspace(
        Workspace(workspace, "Sync workspace"), now=now
    )
    catalog = SqliteCatalogStore(path, migration_now=now)
    catalog.create_asset(
        workspace,
        CatalogAsset(
            source_ref.asset_id,
            "table",
            "Source",
            properties=(
                ("ronin.connector_id", "postgres"),
                ("ronin.connection_ref", "connection-1"),
                ("ronin.asset_ref", "connection-1::table"),
            ),
        ),
        now=now,
    )
    catalog.create_asset(workspace, CatalogAsset(target_ref.asset_id, "table", "Target"), now=now)
    checkpoints = SqliteConnectorCheckpointStore(path)
    identity = "workspace-sync/checkpoint"
    fence = checkpoints.acquire(identity)
    edge = LineageEdge(
        source_ref, target_ref, operation="write", mode="observed", execution_ref="run-1"
    )
    with pytest.raises(ValueError, match="source revision does not exist"):
        checkpoints.commit_output_then_checkpoint(
            identity,
            None,
            SourceCheckpoint("snapshot", "next"),
            output_id="artifact:sync-output",
            output_digest="b" * 64,
            fence=fence,
            output_committed=True,
            catalog_commit=(
                workspace,
                AssetRevision(target_ref, content_digest="b" * 64),
                edge,
                str(now),
                ("postgres", "connection-1", "connection-1::table"),
            ),
        )
    assert checkpoints.get(identity) is None
    assert catalog.get_revision(workspace, target_ref) is None
    assert catalog.upstream(workspace, target_ref) == ()


def test_checkpoint_commit_is_fenced_and_records_output(tmp_path) -> None:
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoints.db")
    identity = "project/source/table"
    assert store.get(identity) is None
    fence = store.acquire(identity)
    next_checkpoint = SourceCheckpoint("watermark", "42")
    evidence = store.commit_output_then_checkpoint(
        identity,
        None,
        next_checkpoint,
        output_id="artifact:batch-1",
        output_digest="sha256:output-1",
        fence=fence,
        output_committed=True,
    )
    assert evidence.next_digest == next_checkpoint.digest
    assert store.get(identity) == next_checkpoint
    recovered = store.get_evidence(identity)
    assert recovered is not None
    assert recovered.output_id == "artifact:batch-1"
    assert recovered.output_digest == "sha256:output-1"
    assert recovered.previous_digest != recovered.next_digest
    assert recovered.to_payload()["schema"] == "ronin.connector-checkpoint-evidence/v1"
    assert recovered.to_payload()["fence"] == fence


def test_checkpoint_rejects_stale_owner_and_cas_replay(tmp_path) -> None:
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoints.db")
    identity = "project/source/table"
    first_fence = store.acquire(identity)
    second_fence = store.acquire(identity)
    checkpoint = SourceCheckpoint("cursor", "a")
    with pytest.raises(CheckpointFenceConflict, match="stale"):
        store.commit_output_then_checkpoint(
            identity,
            None,
            checkpoint,
            output_id="artifact:old",
            output_digest="sha256:old",
            fence=first_fence,
            output_committed=True,
        )
    store.commit_output_then_checkpoint(
        identity,
        None,
        checkpoint,
        output_id="artifact:new",
        output_digest="sha256:new",
        fence=second_fence,
        output_committed=True,
    )
    with pytest.raises(CheckpointFenceConflict, match="CAS"):
        store.commit_output_then_checkpoint(
            identity,
            SourceCheckpoint("cursor", "wrong"),
            SourceCheckpoint("cursor", "b"),
            output_id="artifact:replay",
            output_digest="sha256:replay",
            fence=second_fence,
            output_committed=True,
        )


def test_checkpoint_replay_of_same_output_is_idempotent(tmp_path) -> None:
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoints.db")
    identity = "project/source/table"
    fence = store.acquire(identity)
    checkpoint = SourceCheckpoint("cursor", "a")
    first = store.commit_output_then_checkpoint(
        identity,
        None,
        checkpoint,
        output_id="artifact:batch-1",
        output_digest="sha256:batch-1",
        fence=fence,
        output_committed=True,
    )
    replay = store.commit_output_then_checkpoint(
        identity,
        checkpoint,
        checkpoint,
        output_id="artifact:batch-1",
        output_digest="sha256:batch-1",
        fence=fence,
        output_committed=True,
    )
    assert replay.identity == first.identity
    assert replay.next_digest == first.next_digest
    assert replay.output_id == first.output_id


def test_checkpoint_replay_survives_process_restart(tmp_path) -> None:
    path = tmp_path / "checkpoints.db"
    identity = "project/source/table"
    first_store = SqliteConnectorCheckpointStore(path)
    fence = first_store.acquire(identity)
    checkpoint = SourceCheckpoint("cursor", "restart-safe")
    first = first_store.commit_output_then_checkpoint(
        identity,
        None,
        checkpoint,
        output_id="artifact:batch-restart",
        output_digest="sha256:batch-restart",
        fence=fence,
        output_committed=True,
    )

    reopened = SqliteConnectorCheckpointStore(path)
    replay = reopened.commit_output_then_checkpoint(
        identity,
        checkpoint,
        checkpoint,
        output_id="artifact:batch-restart",
        output_digest="sha256:batch-restart",
        fence=fence,
        output_committed=True,
    )
    assert reopened.get(identity) == checkpoint
    assert replay == first


def test_checkpoint_requires_output_commit_acknowledgement(tmp_path) -> None:
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoints.db")
    fence = store.acquire("project/source/table")
    with pytest.raises(CheckpointFenceConflict, match="before output commit"):
        store.commit_output_then_checkpoint(
            "project/source/table",
            None,
            SourceCheckpoint("cursor", "a"),
            output_id="artifact:batch-1",
            output_digest="sha256:batch-1",
            fence=fence,
            output_committed=False,
        )


def test_checkpoint_rejects_invalid_identity_and_output_digest(tmp_path) -> None:
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoints.db")
    with pytest.raises(ValueError, match="identity"):
        store.acquire("source\nidentity")
    fence = store.acquire("project/source/table")
    checkpoint = SourceCheckpoint("cursor", "a")
    with pytest.raises(ValueError, match="output_id"):
        store.commit_output_then_checkpoint(
            "project/source/table",
            None,
            checkpoint,
            output_id=" output",
            output_digest="a" * 64,
            fence=fence,
            output_committed=True,
        )
    with pytest.raises(ValueError, match="output_digest"):
        store.commit_output_then_checkpoint(
            "project/source/table",
            None,
            checkpoint,
            output_id="output",
            output_digest=" output-digest",
            fence=fence,
            output_committed=True,
        )


def test_checkpoint_health_reports_output_commit(tmp_path):
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoint.sqlite")
    identity = "source/table"
    assert not store.health(identity).present
    fence = store.acquire(identity)
    health = store.health(identity)
    assert not health.present
    assert health.fence == fence
    assert not health.output_committed


def test_checkpoint_fence_placeholder_is_not_an_incremental_checkpoint(tmp_path):
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoint.sqlite")
    identity = "source/table"
    fence = store.acquire(identity)

    assert store.get(identity) is None
    health = store.health(identity)
    assert not health.present
    assert not health.output_committed
    assert health.fence == fence
    assert health.checkpoint_digest is None


def test_committed_connector_artifacts_are_discovered_with_digest_validation(tmp_path):
    store = SqliteConnectorCheckpointStore(tmp_path / "checkpoint.sqlite")
    identity = "source/table"
    store.acquire("source/pending")
    fence = store.acquire(identity)
    digest = sha256(b"connector output").hexdigest()
    store.commit_output_then_checkpoint(
        identity,
        None,
        SourceCheckpoint("cursor", "1"),
        output_id=f"artifact://sha256/{digest}",
        output_digest=digest,
        fence=fence,
        output_committed=True,
    )
    assert discover_connector_artifact_references(store) == {"connector_sync_outputs": (digest,)}
