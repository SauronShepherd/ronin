from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from studio_core import (
    Pipeline,
    WorkflowDefinition,
    WorkflowId,
    Workspace,
    WorkspaceId,
)
from studio_core.scheduler_events import EventTriggerDefinition, EventTriggerId, SchedulerEventId
from studio_orchestrator import Instant
from studio_storage.scheduler_events import SchedulerEventStore
from studio_storage.workspaces import SqliteWorkspaceStore
from studio_streaming import (
    KafkaInputRejected,
    KafkaStreamingRuntime,
    ParquetMicroBatchSink,
    SqliteStreamCheckpointStore,
    SqliteStreamTable,
    StreamBatch,
    StreamCheckpoint,
    StreamDefinition,
    StreamingInputRejected,
    StreamingRunUnavailable,
    StreamPosition,
    StreamRecord,
    StreamRuntimeBinding,
    StreamSchemaField,
    StreamSinkDefinition,
    StreamSourceDefinition,
)

EVENT_NOW = Instant("2026-11-18T10:00:00.000000Z")


class _Source:
    def poll(self, checkpoint, *, limit, timeout_seconds):
        assert limit == 4
        assert timeout_seconds == 0.0
        if checkpoint.positions:
            return StreamBatch((), checkpoint)
        record = StreamRecord(0, 0, 1, "event-1", {"event": "created"})
        return StreamBatch((record,), StreamCheckpoint((StreamPosition(0, 0),)))


def _definition(*, partitions: tuple[int, ...] = (0,)) -> StreamDefinition:
    return StreamDefinition(
        id="events/main",
        name="Events",
        source=StreamSourceDefinition("kafka-local", "events", partitions),
        sink=StreamSinkDefinition("table", "events-table"),
        schema=(StreamSchemaField("event", "string", nullable=False),),
        runtime=StreamRuntimeBinding("local", batch_limit=4, timeout_seconds=0.0),
    )


def _parquet_definition() -> StreamDefinition:
    return StreamDefinition(
        id="events/main",
        name="Events",
        source=StreamSourceDefinition("kafka-local", "events", (0,)),
        sink=StreamSinkDefinition("parquet", "events-parquet"),
        schema=(StreamSchemaField("event", "string", nullable=False),),
        runtime=StreamRuntimeBinding("local", batch_limit=4, timeout_seconds=0.0),
    )


def test_runtime_processes_once_and_persists_sink_before_checkpoint(tmp_path: Path) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    factory_calls = []

    def source_factory(**kwargs):
        factory_calls.append(kwargs)
        return _Source()

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=source_factory,
    )

    result = runtime.run_once(workspace, stream_id)
    replay = runtime.run_once(workspace, stream_id)
    runtime_id = checkpoints.runtime_stream_id(workspace, stream_id)
    table = SqliteStreamTable(tmp_path / "data" / "streaming.sqlite3")

    assert result["status"] == "succeeded"
    assert result["records"] == 1
    assert result["rows"] == 1
    assert result["sink_commit_id"]
    assert replay["status"] == "idle"
    assert replay["records"] == 0
    assert checkpoints.get(runtime_id).offset_for(0) == 0
    assert [(item.offset, item.value["event"]) for item in table.read(runtime_id)] == [
        (0, "created")
    ]
    assert len(factory_calls) == 2
    assert factory_calls[0]["bootstrap_servers"] == "broker:9092"


def test_runtime_ingests_committed_records_into_scheduler_event_inbox(tmp_path: Path) -> None:
    workspace = WorkspaceId("workspace-a")
    stream_id = "events/main"
    database = tmp_path / "state.sqlite3"
    SqliteWorkspaceStore(database, migration_now=EVENT_NOW).create_workspace(
        Workspace(workspace, "Workspace"),
        now=EVENT_NOW,
    )
    event_store = SchedulerEventStore(database, migration_now=EVENT_NOW)
    event_store.put_workflow(
        workspace,
        WorkflowDefinition(WorkflowId("workflow-a"), "Workflow", Pipeline()),
        now=EVENT_NOW,
    )
    event_store.put_event_trigger(
        workspace,
        EventTriggerDefinition(
            EventTriggerId("trigger-a"),
            WorkflowId("workflow-a"),
            "stream.record",
            source_ref=stream_id,
        ),
        now=EVENT_NOW,
    )
    checkpoints = SqliteStreamCheckpointStore(database)
    checkpoints.commit_stream_bundle_import(workspace.value, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=lambda **_kwargs: _Source(),
        event_store=event_store,
        clock=lambda: EVENT_NOW,
    )

    result = runtime.run_once(workspace.value, stream_id)

    event_id = SchedulerEventId("stream-events/main-0-0")
    event = event_store.get_event(workspace, event_id)
    deliveries = event_store.list_event_deliveries(workspace)
    assert result["status"] == "succeeded"
    assert event is not None
    assert event.event_type == "stream.record"
    assert event.source_ref == stream_id
    assert len(deliveries) == 1
    assert deliveries[0].event_id == event_id
    assert deliveries[0].trigger.id == EventTriggerId("trigger-a")


def test_runtime_retries_after_event_store_failure_without_duplicate_sink_or_delivery(
    tmp_path: Path,
) -> None:
    workspace = WorkspaceId("workspace-a")
    stream_id = "events/main"
    database = tmp_path / "state.sqlite3"
    SqliteWorkspaceStore(database, migration_now=EVENT_NOW).create_workspace(
        Workspace(workspace, "Workspace"),
        now=EVENT_NOW,
    )
    event_store = SchedulerEventStore(database, migration_now=EVENT_NOW)
    event_store.put_workflow(
        workspace,
        WorkflowDefinition(WorkflowId("workflow-a"), "Workflow", Pipeline()),
        now=EVENT_NOW,
    )
    event_store.put_event_trigger(
        workspace,
        EventTriggerDefinition(
            EventTriggerId("trigger-a"),
            WorkflowId("workflow-a"),
            "stream.record",
            source_ref=stream_id,
        ),
        now=EVENT_NOW,
    )
    checkpoints = SqliteStreamCheckpointStore(database)
    checkpoints.commit_stream_bundle_import(workspace.value, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )

    class _FailAfterPersistingEvent:
        def __init__(self) -> None:
            self.failed = False

        def ingest_event(self, record):
            deliveries = event_store.ingest_event(record)
            if not self.failed:
                self.failed = True
                raise RuntimeError("simulated checkpoint-boundary failure")
            return deliveries

    failing_store = _FailAfterPersistingEvent()
    first_runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=lambda **_kwargs: _Source(),
        event_store=failing_store,
        clock=lambda: EVENT_NOW,
    )

    with pytest.raises(StreamingRunUnavailable):
        first_runtime.run_once(workspace.value, stream_id)

    runtime_id = checkpoints.runtime_stream_id(workspace.value, stream_id)
    event_id = SchedulerEventId("stream-events/main-0-0")
    table = SqliteStreamTable(tmp_path / "data" / "streaming.sqlite3")
    assert checkpoints.get(runtime_id) == StreamCheckpoint()
    assert event_store.get_event(workspace, event_id) is not None
    assert len(event_store.list_event_deliveries(workspace)) == 1
    assert len(table.read(runtime_id)) == 1

    retry_runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=lambda **_kwargs: _Source(),
        event_store=event_store,
        clock=lambda: EVENT_NOW,
    )
    result = retry_runtime.run_once(workspace.value, stream_id)

    assert result["status"] == "succeeded"
    assert checkpoints.get(runtime_id).offset_for(0) == 0
    assert len(table.read(runtime_id)) == 1
    assert len(event_store.list_event_deliveries(workspace)) == 1


def test_runtime_supervisor_drains_until_idle_with_bounded_provider_polls(
    tmp_path: Path,
) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    source_instances = []
    source = _Source()

    def source_factory(**_kwargs):
        source_instances.append(source)
        return source

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=source_factory,
    )

    result = runtime.run_until_idle(workspace, stream_id, max_batches=3)

    assert result["status"] == "succeeded"
    assert result["stop_reason"] == "idle"
    assert result["batches"] == 1
    assert result["records"] == 1
    assert result["rows"] == 1
    assert len(source_instances) == 1


def test_runtime_supervisor_reuses_source_session_for_all_partitions(
    tmp_path: Path,
) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    definition = _definition(partitions=(0, 1))
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (definition,), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    source_instances = []

    class _PartitionedSource:
        def __init__(self) -> None:
            self.responses = [
                StreamBatch(
                    (StreamRecord(0, 0, 1, "event-0", {"event": "partition-0"}),),
                    StreamCheckpoint((StreamPosition(0, 0),)),
                ),
                StreamBatch(
                    (StreamRecord(1, 0, 1, "event-1", {"event": "partition-1"}),),
                    StreamCheckpoint((StreamPosition(0, 0), StreamPosition(1, 0))),
                ),
            ]

        def poll(self, checkpoint, *, limit, timeout_seconds):
            assert limit == 4
            assert timeout_seconds == 0.0
            if self.responses:
                return self.responses.pop(0)
            return StreamBatch((), checkpoint)

    def source_factory(**_kwargs):
        source = _PartitionedSource()
        source_instances.append(source)
        return source

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=source_factory,
    )

    result = runtime.run_until_idle(workspace, stream_id, max_batches=3, idle_polls=1)

    runtime_id = checkpoints.runtime_stream_id(workspace, stream_id)
    table = SqliteStreamTable(tmp_path / "data" / "streaming.sqlite3")
    assert result["status"] == "succeeded"
    assert result["stop_reason"] == "idle"
    assert result["records"] == 2
    assert result["rows"] == 2
    assert len(source_instances) == 1
    assert [item.partition for item in table.read(runtime_id)] == [0, 1]


def test_runtime_supervisor_stops_at_max_batches_without_losing_checkpoint(tmp_path: Path) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )

    class _ContinuousSource:
        def poll(self, checkpoint, *, limit, timeout_seconds):
            del limit, timeout_seconds
            previous = checkpoint.offset_for(0)
            offset = 0 if previous is None else previous + 1
            record = StreamRecord(0, offset, 1, f"event-{offset}", {"event": "created"})
            return StreamBatch((record,), StreamCheckpoint((StreamPosition(0, offset),)))

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=lambda **_kwargs: _ContinuousSource(),
    )

    result = runtime.run_until_idle(workspace, stream_id, max_batches=2)

    runtime_id = checkpoints.runtime_stream_id(workspace, stream_id)
    assert result["status"] == "limit_reached"
    assert result["stop_reason"] == "max_batches"
    assert result["batches"] == 2
    assert result["records"] == 2
    assert checkpoints.get(runtime_id).offset_for(0) == 1


def test_runtime_supervisor_stops_at_max_records_and_resumes_checkpoint(
    tmp_path: Path,
) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    source_instances = []

    class _ContinuousSource:
        def __init__(self) -> None:
            self.closed = False

        def poll(self, checkpoint, *, limit, timeout_seconds):
            del limit, timeout_seconds
            previous = checkpoint.offset_for(0)
            offset = 0 if previous is None else previous + 1
            record = StreamRecord(0, offset, 1, f"event-{offset}", {"event": "created"})
            return StreamBatch((record,), StreamCheckpoint((StreamPosition(0, offset),)))

        def close(self) -> None:
            self.closed = True

    def source_factory(**_kwargs):
        source = _ContinuousSource()
        source_instances.append(source)
        return source

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=source_factory,
    )

    first = runtime.run_until_idle(workspace, stream_id, max_batches=10, max_records=2)
    second = runtime.run_until_idle(workspace, stream_id, max_batches=10, max_records=2)

    runtime_id = checkpoints.runtime_stream_id(workspace, stream_id)
    table = SqliteStreamTable(tmp_path / "data" / "streaming.sqlite3")
    assert first["status"] == "limit_reached"
    assert first["stop_reason"] == "max_records"
    assert first["records"] == 2
    assert first["rows"] == 2
    assert second["status"] == "limit_reached"
    assert second["stop_reason"] == "max_records"
    assert second["records"] == 2
    assert second["rows"] == 2
    assert checkpoints.get(runtime_id).offset_for(0) == 3
    assert [item.offset for item in table.read(runtime_id)] == [0, 1, 2, 3]
    assert len(source_instances) == 2
    assert all(source.closed for source in source_instances)


def test_runtime_supervisor_bounded_soak_preserves_checkpoint_and_sink_across_segments(
    tmp_path: Path,
) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    source_instances = []
    segment_size = 256
    segments = 4

    class _ContinuousSource:
        def __init__(self) -> None:
            self.closed = False
            self.polls = 0
            self.limits = []

        def poll(self, checkpoint, *, limit, timeout_seconds):
            assert 1 <= limit <= 4
            assert timeout_seconds == 0.0
            previous = checkpoint.offset_for(0)
            offset = 0 if previous is None else previous + 1
            self.polls += 1
            self.limits.append(limit)
            record = StreamRecord(0, offset, 1, f"event-{offset}", {"event": "created"})
            return StreamBatch((record,), StreamCheckpoint((StreamPosition(0, offset),)))

        def close(self) -> None:
            self.closed = True

    def source_factory(**_kwargs):
        source = _ContinuousSource()
        source_instances.append(source)
        return source

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=source_factory,
    )

    runtime_id = checkpoints.runtime_stream_id(workspace, stream_id)
    table = SqliteStreamTable(tmp_path / "data" / "streaming.sqlite3")
    for segment in range(segments):
        before = checkpoints.get(runtime_id)
        result = runtime.run_until_idle(
            workspace,
            stream_id,
            max_batches=segment_size * 2,
            max_records=segment_size,
            idle_polls=1,
        )
        after = checkpoints.get(runtime_id)
        expected_offset = (segment + 1) * segment_size - 1

        assert result["status"] == "limit_reached"
        assert result["stop_reason"] == "max_records"
        assert result["batches"] == segment_size
        assert result["records"] == segment_size
        assert result["rows"] == segment_size
        assert result["previous_checkpoint"] == before.digest
        assert result["checkpoint"] == after.digest
        assert after.offset_for(0) == expected_offset
        assert len(table.read(runtime_id, limit=10_000)) == (segment + 1) * segment_size

    rows = table.read(runtime_id, limit=10_000)
    assert [item.offset for item in rows] == list(range(segment_size * segments))
    assert len(source_instances) == segments
    assert [source.polls for source in source_instances] == [segment_size] * segments
    assert all(source.limits == [4] * (segment_size - 3) + [3, 2, 1] for source in source_instances)
    assert all(source.closed for source in source_instances)


def test_runtime_supervisor_bounded_soak_persists_parquet_and_replays_after_reset(
    tmp_path: Path,
) -> None:
    from studio_lakehouse import read_parquet_rows

    workspace = "workspace-a"
    stream_id = "events/main"
    definition = _parquet_definition()
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (definition,), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    source_instances = []
    segment_size = 16
    segments = 4

    class _ContinuousSource:
        def __init__(self) -> None:
            self.closed = False
            self.polls = 0
            self.limits = []

        def poll(self, checkpoint, *, limit, timeout_seconds):
            assert 1 <= limit <= 4
            assert timeout_seconds == 0.0
            previous = checkpoint.offset_for(0)
            offset = 0 if previous is None else previous + 1
            self.polls += 1
            self.limits.append(limit)
            record = StreamRecord(0, offset, 1, f"event-{offset}", {"event": f"created-{offset}"})
            return StreamBatch((record,), StreamCheckpoint((StreamPosition(0, offset),)))

        def close(self) -> None:
            self.closed = True

    def source_factory(**_kwargs):
        source = _ContinuousSource()
        source_instances.append(source)
        return source

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=source_factory,
    )

    runtime_id = checkpoints.runtime_stream_id(workspace, stream_id)
    parquet_root = tmp_path / "data" / "streaming"

    def parquet_files() -> tuple[Path, ...]:
        return tuple(sorted(parquet_root.rglob("*.parquet")))

    for segment in range(segments):
        result = runtime.run_until_idle(
            workspace,
            stream_id,
            max_batches=segment_size * 2,
            max_records=segment_size,
            idle_polls=1,
        )
        expected_records = (segment + 1) * segment_size
        assert result["status"] == "limit_reached"
        assert result["stop_reason"] == "max_records"
        assert result["batches"] == segment_size
        assert result["records"] == segment_size
        assert result["rows"] == segment_size
        assert checkpoints.get(runtime_id).offset_for(0) == expected_records - 1
        files = parquet_files()
        assert len(files) == expected_records
        offsets = sorted(
            int(row["event"].split("-", 1)[1])
            for path in files
            for row in read_parquet_rows(path)
        )
        assert offsets == list(range(expected_records))

    checkpoints.commit_stream_bundle_import(workspace, (definition,), {stream_id: "reset"})
    replay = runtime.run_until_idle(
        workspace,
        stream_id,
        max_batches=2,
        max_records=1,
        idle_polls=1,
    )

    assert replay["status"] == "limit_reached"
    assert replay["stop_reason"] == "max_records"
    assert replay["records"] == 1
    assert checkpoints.get(runtime_id).offset_for(0) == 0
    assert len(parquet_files()) == segment_size * segments
    assert len(source_instances) == segments + 1
    assert [source.polls for source in source_instances] == [segment_size] * segments + [1]
    assert all(source.closed for source in source_instances)
    assert all(
        source.limits == [4] * (segment_size - 3) + [3, 2, 1]
        for source in source_instances[:segments]
    )
    assert source_instances[-1].limits == [1]


def test_runtime_supervisor_rejects_unbounded_or_empty_caps(tmp_path: Path) -> None:
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(
        "workspace-a", (_definition(),), {"events/main": "reset"}
    )
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=lambda **_kwargs: pytest.fail(
            "invalid caps must fail before source creation"
        ),
    )

    with pytest.raises(ValueError, match="max_batches"):
        runtime.run_until_idle("workspace-a", "events/main", max_batches=0)
    with pytest.raises(ValueError, match="max_records"):
        runtime.run_until_idle("workspace-a", "events/main", max_records=0)
    with pytest.raises(ValueError, match="idle_polls"):
        runtime.run_until_idle("workspace-a", "events/main", idle_polls=0)


def test_runtime_rejects_secret_bootstrap_endpoint(tmp_path: Path) -> None:
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(
        "workspace-a", (_definition(),), {"events/main": "reset"}
    )
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(),
        secret_refs=(("bootstrap.servers", object()),),
    )
    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection: connection,
        lambda _reference: "broker:9092",
        tmp_path / "data",
        source_factory=lambda **_kwargs: pytest.fail("source must not be created"),
    )

    with pytest.raises(StreamingRunUnavailable, match="non-secret"):
        runtime.run_once("workspace-a", "events/main")


def test_runtime_replays_sink_commit_after_checkpoint_compare_and_set_conflict(
    tmp_path: Path,
) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    durable = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    durable.commit_stream_bundle_import(workspace, (_definition(),), {stream_id: "reset"})

    class _FailOnceCheckpointStore:
        def __init__(self):
            self.failed = False

        def runtime_stream_id(self, scoped_workspace, scoped_stream):
            return durable.runtime_stream_id(scoped_workspace, scoped_stream)

        def get_definition(self, scoped_workspace, scoped_stream):
            return durable.get_definition(scoped_workspace, scoped_stream)

        def get(self, runtime_id):
            return durable.get(runtime_id)

        def compare_and_set(self, runtime_id, expected, next_checkpoint):
            if not self.failed:
                self.failed = True
                return False
            return durable.compare_and_set(runtime_id, expected, next_checkpoint)

    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )
    runtime = KafkaStreamingRuntime(
        _FailOnceCheckpointStore(),
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=lambda **_kwargs: _Source(),
    )

    with pytest.raises(StreamingRunUnavailable, match="micro-batch execution failed"):
        runtime.run_once(workspace, stream_id)
    recovered = runtime.run_once(workspace, stream_id)
    runtime_id = durable.runtime_stream_id(workspace, stream_id)
    table = SqliteStreamTable(tmp_path / "data" / "streaming.sqlite3")

    assert recovered["status"] == "succeeded"
    assert durable.get(runtime_id).offset_for(0) == 0
    assert [(item.offset, item.value["event"]) for item in table.read(runtime_id)] == [
        (0, "created")
    ]


def test_runtime_does_not_advance_checkpoint_after_poison_message(tmp_path: Path) -> None:
    workspace = "workspace-a"
    stream_id = "events/main"
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "state.sqlite3")
    checkpoints.commit_stream_bundle_import(workspace, (_definition(),), {stream_id: "reset"})
    connection = SimpleNamespace(
        connector_id="kafka",
        options=(("bootstrap.servers", "broker:9092"),),
        secret_refs=(),
    )

    class _PoisonSource:
        def poll(self, checkpoint, *, limit, timeout_seconds):
            del checkpoint, limit, timeout_seconds
            raise KafkaInputRejected("Kafka message value is not valid UTF-8 JSON")

    runtime = KafkaStreamingRuntime(
        checkpoints,
        lambda _workspace, _connection_id: connection,
        lambda _reference: "unused",
        tmp_path / "data",
        source_factory=lambda **_kwargs: _PoisonSource(),
    )

    with pytest.raises(
        StreamingInputRejected, match="invalid or exceeds local processing limits"
    ) as error:
        runtime.run_once(workspace, stream_id)

    runtime_id = checkpoints.runtime_stream_id(workspace, stream_id)
    table = SqliteStreamTable(tmp_path / "data" / "streaming.sqlite3")
    assert str(error.value) == "stream input is invalid or exceeds local processing limits"
    assert checkpoints.get(runtime_id) == StreamCheckpoint()
    assert table.read(runtime_id) == ()


def test_parquet_sink_replays_identical_checkpoint_without_duplicate_output(
    tmp_path: Path,
) -> None:
    from studio_lakehouse import read_parquet_rows

    record = StreamRecord(0, 4, 1, "event-4", {"event": "created"})
    batch = StreamBatch((record,), StreamCheckpoint((StreamPosition(0, 4),)))
    rows = ({"event": "created"},)
    sink = ParquetMicroBatchSink(tmp_path / "warehouse")

    first = sink.write("events/main", batch, rows)
    replay = sink.write("events/main", batch, rows)

    assert replay == first
    files = tuple((tmp_path / "warehouse").rglob("*.parquet"))
    assert len(files) == 1
    assert read_parquet_rows(files[0]) == rows

    with pytest.raises(RuntimeError, match="conflicts with replayed row content"):
        sink.write("events/main", batch, ({"event": "changed"},))
