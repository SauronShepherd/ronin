from pathlib import Path

import pytest

from studio_streaming import (
    MicroBatchProcessor,
    ParquetMicroBatchSink,
    SqliteStreamCheckpointStore,
    StreamBatch,
    StreamCheckpoint,
    StreamCheckpointConflict,
    StreamPosition,
    StreamRecord,
    StreamSinkCommit,
)


class _Source:
    def __init__(self, batch: StreamBatch) -> None:
        self.batch = batch
        self.checkpoints = []

    def poll(self, checkpoint, *, limit, timeout_seconds):
        del limit, timeout_seconds
        self.checkpoints.append(checkpoint)
        return self.batch


class _FailingSink:
    def write(self, stream_id, batch, rows):
        del stream_id, batch, rows
        raise RuntimeError("sink failed")


class _MemorySink:
    def __init__(self) -> None:
        self.commits = []

    def write(self, stream_id, batch, rows):
        commit = StreamSinkCommit(
            f"commit:{stream_id}:{batch.checkpoint.digest}",
            len(rows),
            batch.checkpoint.digest,
        )
        self.commits.append(commit)
        return commit


class _ConflictingCheckpointStore:
    def __init__(self) -> None:
        self.initial = StreamCheckpoint()

    def get(self, stream_id):
        del stream_id
        return self.initial

    def compare_and_set(self, stream_id, expected, next_checkpoint):
        del stream_id, expected, next_checkpoint
        return False


def _batch() -> StreamBatch:
    checkpoint = StreamCheckpoint((StreamPosition(0, 1),))
    return StreamBatch(
        (
            StreamRecord(0, 0, None, None, {"id": 1}),
            StreamRecord(0, 1, None, None, {"id": 2}),
        ),
        checkpoint,
    )


def test_sink_failure_does_not_advance_checkpoint(tmp_path: Path) -> None:
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "checkpoints.sqlite")
    processor = MicroBatchProcessor(_Source(_batch()), _FailingSink(), checkpoints)
    with pytest.raises(RuntimeError, match="sink failed"):
        processor.run_once("orders")
    assert checkpoints.get("orders") == StreamCheckpoint()


def test_successful_sink_commit_advances_checkpoint(tmp_path: Path) -> None:
    checkpoints = SqliteStreamCheckpointStore(tmp_path / "checkpoints.sqlite")
    sink = _MemorySink()
    processor = MicroBatchProcessor(_Source(_batch()), sink, checkpoints)
    result = processor.run_once("orders")
    assert result.records == 2
    assert result.rows == 2
    assert checkpoints.get("orders") == _batch().checkpoint
    assert sink.commits == [result.sink_commit]


def test_cas_conflict_surfaces_after_replay_safe_sink_commit() -> None:
    sink = _MemorySink()
    processor = MicroBatchProcessor(
        _Source(_batch()),
        sink,
        _ConflictingCheckpointStore(),
    )
    with pytest.raises(StreamCheckpointConflict, match="changed after sink commit"):
        processor.run_once("orders")
    assert len(sink.commits) == 1


def test_parquet_sink_replays_same_checkpoint_idempotently(tmp_path: Path) -> None:
    pytest.importorskip("pyarrow")
    sink = ParquetMicroBatchSink(tmp_path / "warehouse")
    batch = _batch()
    rows = tuple(record.value for record in batch.records)
    first = sink.write("orders", batch, rows)
    second = sink.write("orders", batch, rows)
    assert second == first
    assert first.rows == 2


def test_checkpoint_store_compare_and_set_rejects_stale_expected(tmp_path: Path) -> None:
    store = SqliteStreamCheckpointStore(tmp_path / "checkpoints.sqlite")
    first = StreamCheckpoint((StreamPosition(0, 10),))
    second = StreamCheckpoint((StreamPosition(0, 20),))
    assert store.compare_and_set("orders", StreamCheckpoint(), first)
    assert not store.compare_and_set("orders", StreamCheckpoint(), second)
    assert store.get("orders") == first
