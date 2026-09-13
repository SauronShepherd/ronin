"""Streaming and real-time micro-batch runtime for Ronin Public v1."""

from .checkpoint import SqliteStreamCheckpointStore
from .contracts import (
    StreamBatch,
    StreamCheckpoint,
    StreamCheckpointStore,
    StreamPosition,
    StreamRecord,
    StreamSink,
    StreamSinkCommit,
    StreamSource,
)
from .kafka import KafkaDependencyError, KafkaJsonSource
from .parquet_sink import ParquetMicroBatchSink
from .processor import (
    IdentityTransform,
    MicroBatchProcessor,
    MicroBatchResult,
    StreamCheckpointConflict,
    StreamTransform,
)

__all__ = (
    "IdentityTransform",
    "KafkaDependencyError",
    "KafkaJsonSource",
    "MicroBatchProcessor",
    "MicroBatchResult",
    "ParquetMicroBatchSink",
    "SqliteStreamCheckpointStore",
    "StreamBatch",
    "StreamCheckpoint",
    "StreamCheckpointConflict",
    "StreamCheckpointStore",
    "StreamPosition",
    "StreamRecord",
    "StreamSink",
    "StreamSinkCommit",
    "StreamSource",
    "StreamTransform",
)
