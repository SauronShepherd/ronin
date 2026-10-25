from __future__ import annotations

import os
import socket
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from studio_cli.local_composed import build_local_composed_from_env
from studio_connectors import (
    CheckpointFenceConflict,
    IngestionSyncDefinition,
    PostgresConnectorCheckpointStore,
)
from studio_connectors.http import IngestionHTTPAdapter
from studio_connectors.sync import scoped_checkpoint_identity
from studio_core import (
    ConnectionDefinition,
    ConnectionId,
    SecretRef,
    SourceCheckpoint,
    Workspace,
    WorkspaceId,
)
from studio_execution import ConnectionService, build_connector_sync_dependencies
from studio_orchestrator import Instant
from studio_server.control_plane import WorkspaceProjectHTTPServer
from studio_storage import (
    LocalArtifactStore,
    PostgresMetadataStore,
    discover_connector_artifact_references,
)
from studio_worker import LocalWorkerRuntimeConfig, WorkerPaths

pytestmark = pytest.mark.skipif(
    not os.environ.get("RONIN_POSTGRES_TEST_DSN"),
    reason="real PostgreSQL connector checkpoint qualification requires RONIN_POSTGRES_TEST_DSN",
)


def _available_tcp_ports(count: int) -> tuple[int, ...]:
    sockets = [socket.socket() for _ in range(count)]
    try:
        for probe in sockets:
            probe.bind(("127.0.0.1", 0))
        return tuple(int(probe.getsockname()[1]) for probe in sockets)
    finally:
        for probe in sockets:
            probe.close()


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
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    job_port, control_plane_port = _available_tcp_ports(2)
    monkeypatch.setenv("RONIN_DB", str(tmp_path / "ronin.sqlite3"))
    monkeypatch.setenv("RONIN_WORKSPACE_ID", f"workspace-{uuid4().hex}")
    monkeypatch.setenv("RONIN_CONTROL_PLANE_TOKEN", "control-token")
    monkeypatch.setenv("RONIN_TOKEN", "job-token")
    monkeypatch.setenv("RONIN_PORT", str(job_port))
    monkeypatch.setenv("RONIN_CONTROL_PLANE_PORT", str(control_plane_port))
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
        control_plane = cast(WorkspaceProjectHTTPServer, composition.control_plane_server)
        adapter = cast(IngestionHTTPAdapter | None, control_plane.ingestion_adapter)
        assert adapter is not None
        assert isinstance(adapter._checkpoints, PostgresConnectorCheckpointStore)
        assert adapter._service._artifact_reference_barrier is not None
    finally:
        composition.stop()


def test_postgres_connector_sync_worker_reads_writes_and_advances_scoped_checkpoint(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict

    dsn = os.environ["RONIN_POSTGRES_TEST_DSN"]
    connection_parameters = conninfo_to_dict(dsn)
    if not connection_parameters.get("password"):
        pytest.skip("real connector worker qualification requires password authentication")
    source_schema = f"sync_test_{uuid4().hex}"
    workspace_id = WorkspaceId(f"worker-sync-{uuid4().hex}")
    connection_id = ConnectionId(f"source-{uuid4().hex}")
    metadata = PostgresMetadataStore(dsn, application_name="ronin-test-connector-worker")
    source_user = str(connection_parameters.get("user") or "postgres")
    source_password = str(connection_parameters["password"])
    monkeypatch.setenv("RONIN_SYNC_SOURCE_USER", source_user)
    monkeypatch.setenv("RONIN_SYNC_SOURCE_PASSWORD", source_password)
    with psycopg.connect(dsn) as database, database.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(source_schema)))
        cursor.execute(
            sql.SQL("CREATE TABLE {}.records (id integer PRIMARY KEY, email text NOT NULL)").format(
                sql.Identifier(source_schema)
            )
        )
        cursor.execute(
            sql.SQL("INSERT INTO {}.records VALUES (1, %s), (2, %s)").format(
                sql.Identifier(source_schema)
            ),
            ("a@example.test", "b@example.test"),
        )

    try:
        now = Instant("2026-10-25T00:00:00.000000Z")
        metadata.create_workspace(Workspace(workspace_id, "Worker sync qualification"), now=now)
        connection = ConnectionDefinition(
            connection_id,
            "PostgreSQL source",
            "postgresql",
            (
                ("connect_timeout", "5"),
                ("database", str(connection_parameters["dbname"])),
                ("host", str(connection_parameters.get("host") or "127.0.0.1")),
                ("port", str(connection_parameters.get("port") or "5432")),
                ("schema", source_schema),
            ),
            (
                ("password", SecretRef("secret://env/RONIN_SYNC_SOURCE_PASSWORD")),
                ("user", SecretRef("secret://env/RONIN_SYNC_SOURCE_USER")),
            ),
        )
        ConnectionService(metadata, metadata).create(workspace_id, connection, now=now)
        config = LocalWorkerRuntimeConfig(
            paths=WorkerPaths(tmp_path, tmp_path / "worker-data"),
            owner="postgres-sync-worker-test",
            image="sha256:" + "a" * 64,
            postgres_dsn=dsn,
            connector_workspace_id=str(workspace_id),
        )
        artifacts = LocalArtifactStore(tmp_path / "artifacts")
        dependencies = build_connector_sync_dependencies(
            workspace_id=str(workspace_id),
            postgres_dsn=dsn,
            database_path=config.database_path,
            artifact_store=artifacts,
            artifact_reference_barrier=None,
            migration_now=now,
        )
        asset_ref = f"{source_schema}.records"
        definition = IngestionSyncDefinition(
            id=f"sync-{uuid4().hex}",
            connector_id="postgresql",
            connection_ref=str(connection_id),
            asset_ref=asset_ref,
            destination_ref="artifact://qualification/postgres-sync",
            checkpoint_identity=f"checkpoint-{uuid4().hex}",
            mode="snapshot",
        )
        connection = dependencies.connection(str(workspace_id), definition.connection_ref)
        asset = dependencies.asset(connection, definition.asset_ref)
        secret_resolver = dependencies.secrets(definition.connection_ref)
        first = dependencies.service.execute(
            definition,
            workspace_id=str(workspace_id),
            connection=connection,
            asset=asset,
            secrets=secret_resolver,
            destination=dependencies.destination,
        )
        scoped_identity = scoped_checkpoint_identity(
            str(workspace_id), definition.checkpoint_identity
        )
        checkpoint_store = PostgresConnectorCheckpointStore(dsn)
        first_evidence = checkpoint_store.get_evidence(scoped_identity)
        assert first["rows_written"] == 2
        assert first_evidence is not None
        assert checkpoint_store.health(scoped_identity).output_committed
        first_output = artifacts.get_bytes_by_storage_ref(
            first_evidence.output_id, digest=first_evidence.output_digest
        )
        assert b"a@example.test" in first_output
        assert b"b@example.test" in first_output

        second = dependencies.service.execute(
            definition,
            workspace_id=str(workspace_id),
            connection=connection,
            asset=asset,
            secrets=secret_resolver,
            destination=dependencies.destination,
        )
        assert second["rows_written"] == 0
        assert checkpoint_store.get(scoped_identity) is not None
    finally:
        with psycopg.connect(dsn) as database, database.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(source_schema))
            )
