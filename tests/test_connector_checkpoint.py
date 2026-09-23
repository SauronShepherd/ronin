from __future__ import annotations

import pytest
from studio_connectors import (
    CheckpointFenceConflict,
    SqliteConnectorCheckpointStore,
)
from studio_core import SourceCheckpoint


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
    assert health.present and health.fence == fence and not health.output_committed
