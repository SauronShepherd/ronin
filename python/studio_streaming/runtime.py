"""Bounded Kafka-to-local-sink execution for persisted streaming definitions."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from studio_core import WorkspaceId

from .bundle import (
    MAX_STREAM_BUNDLE_BYTES,
    CheckpointImportPolicy,
    commit_stream_bundle_import,
    export_stream_bundle,
    plan_stream_bundle_import,
)
from .checkpoint import SqliteStreamCheckpointStore
from .contracts import StreamBatch, StreamDefinition, StreamSink, StreamSinkCommit
from .kafka import KafkaDependencyError, KafkaInputRejected, KafkaJsonSource
from .parquet_sink import ParquetMicroBatchSink
from .processor import MicroBatchProcessor, MicroBatchResult
from .table import SqliteStreamTable


class StreamingRunUnavailable(RuntimeError):
    """Raised when a stored stream cannot run with the local runtime."""


class StreamingInputRejected(RuntimeError):
    """Raised when a Kafka batch violates the bounded JSON input contract."""


class _TableSink:
    def __init__(self, table: SqliteStreamTable) -> None:
        self._table = table

    def write(
        self, stream_id: str, batch: StreamBatch, rows: tuple[Mapping[str, object], ...]
    ) -> StreamSinkCommit:
        self._table.append(stream_id, batch)
        return StreamSinkCommit(
            f"sqlite-batch:{batch.checkpoint.digest}", len(rows), batch.checkpoint.digest
        )


class KafkaStreamingRuntime:
    """Execute bounded Kafka micro-batches using Ronin's durable checkpoints."""

    def __init__(
        self,
        checkpoints: SqliteStreamCheckpointStore,
        resolve_connection: Callable[[str, str], Any],
        resolve_secret: Callable[[Any], str],
        data_root: Path,
        *,
        source_factory: Callable[..., Any] = KafkaJsonSource,
        event_store: Any | None = None,
        event_ingestor: Callable[..., Any] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._checkpoints = checkpoints
        self._resolve_connection = resolve_connection
        self._resolve_secret = resolve_secret
        self._data_root = data_root.expanduser().resolve()
        self._source_factory = source_factory
        self._event_store = event_store
        self._event_ingestor = event_ingestor
        self._clock = clock or (
            lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        )

    def _ingest_stream_events(
        self,
        workspace_id: str,
        stream_id: str,
        batch: StreamBatch,
    ) -> None:
        if self._event_store is None or self._event_ingestor is None:
            return
        received_at = self._clock()
        for record in batch.records:
            self._event_ingestor(
                self._event_store,
                record,
                workspace_id=WorkspaceId(workspace_id),
                stream_id=stream_id,
                received_at=received_at,
            )

    def _resolve_run_options(
        self,
        workspace_id: WorkspaceId | str,
        stream_id: str,
        *,
        limit: int | None,
        timeout_seconds: float | None,
    ) -> tuple[str, str, StreamDefinition, int, float]:
        workspace = str(workspace_id)
        runtime_id = self._checkpoints.runtime_stream_id(workspace, stream_id)
        definition = self._checkpoints.get_definition(workspace, stream_id)
        if definition is None:
            raise KeyError(stream_id)
        if definition.runtime.profile_id != "local":
            raise StreamingRunUnavailable(
                "stream runtime profile is not available in this local server"
            )
        batch_limit = definition.runtime.batch_limit if limit is None else limit
        timeout = definition.runtime.timeout_seconds if timeout_seconds is None else timeout_seconds
        if (
            not isinstance(batch_limit, int)
            or isinstance(batch_limit, bool)
            or not 1 <= batch_limit <= 100_000
        ):
            raise ValueError("stream limit must be an integer between 1 and 100000")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 <= timeout <= 300
        ):
            raise ValueError("stream timeout_seconds must be numeric and in [0, 300]")
        return workspace, runtime_id, definition, batch_limit, float(timeout)

    def _build_processor(
        self,
        workspace_id: WorkspaceId | str,
        stream_id: str,
        *,
        limit: int | None,
        timeout_seconds: float | None,
    ) -> tuple[str, MicroBatchProcessor, int, float]:
        workspace, runtime_id, definition, batch_limit, timeout = self._resolve_run_options(
            workspace_id,
            stream_id,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

        connection = self._resolve_connection(workspace, definition.source.connection_id)
        if connection.connector_id not in {"kafka", "apache.kafka"}:
            raise StreamingRunUnavailable("stream source connection is not Kafka")
        options = dict(connection.options)
        if "bootstrap.servers" in dict(connection.secret_refs):
            raise StreamingRunUnavailable("Kafka bootstrap.servers must be a non-secret option")
        bootstrap = options.pop("bootstrap.servers", "").strip()
        if not bootstrap:
            raise StreamingRunUnavailable("Kafka connection has no bootstrap.servers option")
        try:
            options.update(
                {
                    name: self._resolve_secret(reference)
                    for name, reference in connection.secret_refs
                }
            )
        except Exception as exc:
            raise StreamingRunUnavailable("Kafka connection secrets could not be resolved") from exc

        identity = hashlib.sha256(runtime_id.encode("utf-8")).hexdigest()[:24]
        try:
            source = self._source_factory(
                bootstrap_servers=bootstrap,
                topic=definition.source.resource,
                partitions=definition.source.partitions,
                group_id=f"ronin-{identity}",
                client_id=f"ronin-{identity}",
                config=options,
            )
        except KafkaDependencyError as exc:
            raise StreamingRunUnavailable("Kafka streaming dependencies are unavailable") from exc

        sink: StreamSink
        if definition.sink.kind == "table":
            sink = _TableSink(SqliteStreamTable(self._data_root / "streaming.sqlite3"))
        else:
            target = hashlib.sha256(
                f"{workspace}\0{definition.sink.target_ref}".encode()
            ).hexdigest()[:24]
            sink = ParquetMicroBatchSink(self._data_root / "streaming" / target)
        before_checkpoint: Callable[[str, StreamBatch], None] | None = None
        if self._event_store is not None:
            def before_checkpoint(
                _current_stream_id: str,
                current_batch: StreamBatch,
            ) -> None:
                self._ingest_stream_events(workspace, stream_id, current_batch)

        return (
            runtime_id,
            MicroBatchProcessor(
                source,
                sink,
                self._checkpoints,
                before_checkpoint=before_checkpoint,
            ),
            batch_limit,
            timeout,
        )

    def run_once(
        self,
        workspace_id: WorkspaceId | str,
        stream_id: str,
        *,
        limit: int | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        runtime_id, processor, batch_limit, timeout = self._build_processor(
            workspace_id,
            stream_id,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        try:
            result = self._run_processor_once(
                processor,
                runtime_id,
                limit=batch_limit,
                timeout_seconds=timeout,
            )
            return {
                "stream_id": stream_id,
                "status": "succeeded" if result.records else "idle",
                "records": result.records,
                "rows": result.rows,
                "previous_checkpoint": result.previous_checkpoint.digest,
                "checkpoint": result.next_checkpoint.digest,
                "sink_commit_id": None
                if result.sink_commit is None
                else result.sink_commit.commit_id,
            }
        finally:
            processor.close()

    def _run_processor_once(
        self,
        processor: MicroBatchProcessor,
        runtime_id: str,
        *,
        limit: int,
        timeout_seconds: float,
    ) -> MicroBatchResult:
        try:
            return processor.run_once(
                runtime_id,
                limit=limit,
                timeout_seconds=timeout_seconds,
            )
        except KafkaInputRejected as exc:
            raise StreamingInputRejected(
                "stream input is invalid or exceeds local processing limits"
            ) from exc
        except KafkaDependencyError as exc:
            raise StreamingRunUnavailable("Kafka streaming dependencies are unavailable") from exc
        except Exception as exc:
            # Provider exception text can contain endpoints and credentials.
            raise StreamingRunUnavailable("stream micro-batch execution failed") from exc

    def run_until_idle(
        self,
        workspace_id: WorkspaceId | str,
        stream_id: str,
        *,
        limit: int | None = None,
        timeout_seconds: float | None = None,
        max_batches: int = 100,
        max_records: int | None = None,
        idle_polls: int = 3,
    ) -> dict[str, object]:
        """Drain a stream through repeated bounded batches and stop at a cap or idle poll."""

        if (
            not isinstance(max_batches, int)
            or isinstance(max_batches, bool)
            or not 1 <= max_batches <= 100_000
        ):
            raise ValueError("stream max_batches must be an integer between 1 and 100000")
        if max_records is not None and (
            not isinstance(max_records, int)
            or isinstance(max_records, bool)
            or not 1 <= max_records <= 10_000_000
        ):
            raise ValueError("stream max_records must be an integer between 1 and 10000000")
        if (
            not isinstance(idle_polls, int)
            or isinstance(idle_polls, bool)
            or not 1 <= idle_polls <= 10
        ):
            raise ValueError("stream idle_polls must be an integer between 1 and 10")
        runtime_id, processor, batch_limit, timeout = self._build_processor(
            workspace_id,
            stream_id,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )
        previous_checkpoint = self._checkpoints.get(runtime_id).digest
        next_checkpoint = previous_checkpoint
        batches = 0
        records = 0
        rows = 0
        empty_polls = 0
        try:
            while True:
                if batches >= max_batches:
                    status = "limit_reached"
                    stop_reason = "max_batches"
                    break
                remaining = None if max_records is None else max_records - records
                if remaining == 0:
                    status = "limit_reached"
                    stop_reason = "max_records"
                    break
                current_limit = batch_limit if remaining is None else min(batch_limit, remaining)
                result = self._run_processor_once(
                    processor,
                    runtime_id,
                    limit=current_limit,
                    timeout_seconds=timeout,
                )
                batch_records = result.records
                batch_rows = result.rows
                checkpoint = result.next_checkpoint.digest
                next_checkpoint = checkpoint
                if batch_records == 0:
                    empty_polls += 1
                    if empty_polls >= idle_polls:
                        status = "succeeded" if records else "idle"
                        stop_reason = "idle"
                        break
                    continue
                empty_polls = 0
                batches += 1
                records += batch_records
                rows += batch_rows
        finally:
            processor.close()

        return {
            "stream_id": stream_id,
            "status": status,
            "stop_reason": stop_reason,
            "batches": batches,
            "records": records,
            "rows": rows,
            "previous_checkpoint": previous_checkpoint,
            "checkpoint": next_checkpoint,
        }

    def list_definitions(self, workspace_id: WorkspaceId | str) -> dict[str, object]:
        workspace = str(workspace_id)
        definitions = self._checkpoints.list_definitions(workspace)
        return {"items": [definition.to_payload() for definition in definitions]}

    def put_definition(
        self,
        workspace_id: WorkspaceId | str,
        definition: StreamDefinition,
        *,
        checkpoint_policy: str,
    ) -> dict[str, object]:
        workspace = str(workspace_id)
        runtime_ids = self._checkpoints.commit_stream_bundle_import(
            workspace,
            (definition,),
            {definition.id: checkpoint_policy},
        )
        return {
            "definition": definition.to_payload(),
            "checkpoint_policy": checkpoint_policy,
            "runtime_stream_id": dict(runtime_ids)[definition.id],
        }

    def export_bundle(self, workspace_id: WorkspaceId | str) -> bytes:
        """Export all persisted definitions, never their runtime checkpoints."""
        with tempfile.TemporaryDirectory(prefix="ronin-stream-bundle-") as directory:
            path = Path(directory) / "streams.roninbundle"
            export_stream_bundle(str(workspace_id), self._checkpoints, path)
            archive = path.read_bytes()
        if len(archive) > MAX_STREAM_BUNDLE_BYTES:
            raise ValueError("stream Bundle exceeds the 700 KiB export limit")
        return archive

    def plan_bundle(self, archive: bytes) -> dict[str, object]:
        """Verify a Bundle and expose the exact binding and checkpoint choices required."""
        if len(archive) > MAX_STREAM_BUNDLE_BYTES:
            raise ValueError("stream Bundle exceeds the 700 KiB import limit")
        with tempfile.TemporaryDirectory(prefix="ronin-stream-bundle-plan-") as directory:
            path = Path(directory) / "streams.roninbundle"
            path.write_bytes(archive)
            plan = plan_stream_bundle_import(path)
        return {
            "items": [item.to_payload() for item in plan.definitions],
            "unresolved_bindings": [item.to_payload() for item in plan.unresolved_bindings],
        }

    def import_bundle(
        self,
        workspace_id: WorkspaceId | str,
        archive: bytes,
        *,
        binding_remaps: Mapping[str, str],
        checkpoint_policies: Mapping[str, str],
    ) -> dict[str, object]:
        """Verify and atomically import definitions using explicit bindings and offsets."""
        if len(archive) > MAX_STREAM_BUNDLE_BYTES:
            raise ValueError("stream Bundle exceeds the 700 KiB import limit")
        with tempfile.TemporaryDirectory(prefix="ronin-stream-bundle-import-") as directory:
            path = Path(directory) / "streams.roninbundle"
            path.write_bytes(archive)
            typed_checkpoint_policies: dict[str, CheckpointImportPolicy] = {}
            for stream_id, policy in checkpoint_policies.items():
                if policy not in {"reset", "resume"}:
                    raise ValueError("stream checkpoint policy must be reset or resume")
                typed_checkpoint_policies[stream_id] = cast(CheckpointImportPolicy, policy)
            receipt = commit_stream_bundle_import(
                path,
                str(workspace_id),
                self._checkpoints,
                binding_remaps=binding_remaps,
                checkpoint_policies=typed_checkpoint_policies,
            )
        imported_ids = {item.id for item in receipt.plan.definitions}
        imported_definitions = tuple(
            item
            for item in self._checkpoints.list_definitions(str(workspace_id))
            if item.id in imported_ids
        )
        return {
            "items": [item.to_payload() for item in imported_definitions],
            "checkpoint_policies": dict(checkpoint_policies),
            "runtime_bindings": dict(receipt.runtime_bindings),
        }


__all__ = ("KafkaStreamingRuntime", "StreamingInputRejected", "StreamingRunUnavailable")
