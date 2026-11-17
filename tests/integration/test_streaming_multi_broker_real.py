"""Real multi-broker streaming recovery; opt-in because it owns a live broker failure."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Mapping
from pathlib import Path

import pytest
from studio_streaming import KafkaJsonSource, MicroBatchProcessor, SqliteStreamCheckpointStore
from studio_streaming.contracts import StreamBatch, StreamSinkCommit

_BOOTSTRAP = os.environ.get("RONIN_MULTI_BROKER_BOOTSTRAP", "")
_FAILOVER_CONTAINER = os.environ.get("RONIN_MULTI_BROKER_FAILOVER_CONTAINER", "")
_TOPIC = os.environ.get("RONIN_MULTI_BROKER_TOPIC", "ronin-d51-recovery")
_DOCKER = shutil.which("docker")

if not _BOOTSTRAP or not _FAILOVER_CONTAINER or _DOCKER is None:
    pytest.skip(
        "set RONIN_MULTI_BROKER_BOOTSTRAP and RONIN_MULTI_BROKER_FAILOVER_CONTAINER "
        "for the real multi-broker recovery qualification",
        allow_module_level=True,
    )


class _RecordingSink:
    def __init__(self) -> None:
        self.rows: list[Mapping[str, object]] = []

    def write(
        self,
        stream_id: str,
        batch: StreamBatch,
        rows: tuple[Mapping[str, object], ...],
    ) -> StreamSinkCommit:
        self.rows.extend(rows)
        return StreamSinkCommit(
            commit_id=f"multi-broker:{stream_id}:{batch.checkpoint.digest}",
            rows=len(rows),
            checkpoint_digest=batch.checkpoint.digest,
        )


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    assert _DOCKER is not None
    return subprocess.run(  # noqa: S603 - executable is resolved from PATH; args are test constants
        [_DOCKER, *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_real_replicated_kafka_recovers_after_leader_failure(tmp_path: Path) -> None:
    checkpoint_store = SqliteStreamCheckpointStore(tmp_path / "stream-checkpoints.sqlite3")
    sink = _RecordingSink()
    source = KafkaJsonSource(
        bootstrap_servers=_BOOTSTRAP,
        topic=_TOPIC,
        partitions=(0,),
        group_id="ronin-real-multi-broker-recovery",
        client_id="ronin-real-multi-broker-recovery",
    )
    processor = MicroBatchProcessor(source, sink, checkpoint_store)
    stream_id = "events/multi-broker"

    try:
        first = processor.run_once(stream_id, limit=1, timeout_seconds=5)
        assert first.records == 1
        assert len(sink.rows) == 1

        _docker("stop", _FAILOVER_CONTAINER)
        time.sleep(3)

        resumed = processor.run_once(stream_id, limit=4, timeout_seconds=15)
        assert resumed.records == 4
        assert len(sink.rows) == 5
        assert checkpoint_store.get(stream_id) == resumed.next_checkpoint
    finally:
        _docker("start", _FAILOVER_CONTAINER, check=False)
        processor.close()
