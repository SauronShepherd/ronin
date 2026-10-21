from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from studio_cli.local_composed import build_local_composed_from_env
from studio_connectors import CheckpointFenceConflict, PostgresConnectorCheckpointStore
from studio_core import SourceCheckpoint
from studio_storage import discover_connector_artifact_references

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL connector checkpoint qualification requires RONIN_POSTGRES_TEST_DSN",
)


def test_postgres_connector_checkpoint_fencing_inventory_and_restart() -> None:
    store = PostgresConnectorCheckpointStore(os.environ["RONIN_POSTGRES_TEST_DSN"])
    identity = f"retention-checkpoint/{uuid4().hex}"
    artifact_digest = "a" * 64

    assert store.get(identity) is None
    with ThreadPoolExecutor(max_workers=2) as executor:
        fences = sorted(executor.map(lambda _index: store.acquire(identity), range(2)))
    first_fence, fence = fences
    next_checkpoint = SourceCheckpoint("watermark", "42")
    with pytest.raises(CheckpointFenceConflict, match="stale"):
        store.commit_output_then_checkpoint(
            identity,
            None,
            next_checkpoint,
            output_id="artifact://sha256/" + artifact_digest,
            output_digest=artifact_digest,
            fence=first_fence,
            output_committed=True,
        )

    store.commit_output_then_checkpoint(
        identity,
        None,
        next_checkpoint,
        output_id="artifact://sha256/" + artifact_digest,
        output_digest=artifact_digest,
        fence=fence,
        output_committed=True,
    )
    second_identity = f"retention-checkpoint/{uuid4().hex}"
    second_fence = store.acquire(second_identity)
    second_digest = "b" * 64
    store.commit_output_then_checkpoint(
        second_identity,
        None,
        SourceCheckpoint("cursor", "second"),
        output_id="artifact://sha256/" + second_digest,
        output_digest=second_digest,
        fence=second_fence,
        output_committed=True,
    )
    reopened = PostgresConnectorCheckpointStore(os.environ["RONIN_POSTGRES_TEST_DSN"])
    assert reopened.get(identity) == next_checkpoint
    assert reopened.health(identity).output_committed
    evidence = reopened.get_evidence(identity)
    assert evidence is not None
    assert evidence.fence == fence
    assert evidence.output_digest == artifact_digest
    replay = reopened.commit_output_then_checkpoint(
        identity,
        next_checkpoint,
        next_checkpoint,
        output_id="artifact://sha256/" + artifact_digest,
        output_digest=artifact_digest,
        fence=fence,
        output_committed=True,
    )
    assert replay == evidence
    with pytest.raises(CheckpointFenceConflict, match="CAS"):
        reopened.commit_output_then_checkpoint(
            identity,
            SourceCheckpoint("watermark", "wrong"),
            SourceCheckpoint("watermark", "43"),
            output_id="artifact://sha256/" + "c" * 64,
            output_digest="c" * 64,
            fence=fence,
            output_committed=True,
        )
    references = discover_connector_artifact_references(reopened)
    assert artifact_digest in references["connector_sync_outputs"]
    assert second_digest in references["connector_sync_outputs"]
    with pytest.raises(ValueError, match="exceeded its bound"):
        reopened.list_committed_outputs(max_outputs=1)


def test_postgres_local_composition_mounts_shared_connector_ingestion(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", f"workspace-{uuid4().hex}")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "control-token")
    monkeypatch.setenv("RONIN_TOKEN", "job-token")
    monkeypatch.setenv("RONIN_PORT", "18080")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", "18081")
    monkeypatch.setenv("RONIN_STORAGE_BACKEND", "postgres")
    monkeypatch.setenv("RONIN_POSTGRES_DSN", os.environ["RONIN_POSTGRES_TEST_DSN"])
    monkeypatch.setenv(
        "RONIN_TOKEN_SCOPES",
        '{"version":1,"grants":[{"actions":["cancel","evidence:read",'
        '"execute","events","list","read","submit"],"constraints":{},'
        '"resource":{"identifier":null,"kind":"*"},"version":1}]}',
    )

    composition = build_local_composed_from_env()
    try:
        adapter = composition.control_plane_server.ingestion_adapter
        assert adapter is not None
        assert isinstance(adapter._checkpoints, PostgresConnectorCheckpointStore)
        assert adapter._service._artifact_reference_barrier is not None
    finally:
        composition.stop()
