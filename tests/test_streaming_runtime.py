from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from studio_streaming import (
    KafkaInputRejected,
    KafkaStreamingRuntime,
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


class _Source:
    def poll(self, checkpoint, *, limit, timeout_seconds):
        assert limit == 4
        assert timeout_seconds == 0.0
        if checkpoint.positions:
            return StreamBatch((), checkpoint)
        record = StreamRecord(0, 0, 1, "event-1", {"event": "created"})
        return StreamBatch((record,), StreamCheckpoint((StreamPosition(0, 0),)))


def _definition() -> StreamDefinition:
    return StreamDefinition(
        id="events/main",
        name="Events",
        source=StreamSourceDefinition("kafka-local", "events", (0,)),
        sink=StreamSinkDefinition("table", "events-table"),
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
