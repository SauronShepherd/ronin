"""Idempotent Parquet micro-batch sink for the reference streaming runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from studio_lakehouse import inspect_parquet, write_parquet_rows

from .contracts import StreamBatch, StreamSinkCommit


def _safe_stream_id(value: str) -> str:
    if not value or value != value.strip() or "\n" in value or "\r" in value or "\x00" in value:
        raise ValueError("stream_id must be non-empty, trimmed, and single-line")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:32]


class ParquetMicroBatchSink:
    """Write each checkpoint-addressed batch once under a configured warehouse root."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, stream_id: str, batch: StreamBatch) -> Path:
        stream_key = _safe_stream_id(stream_id)
        return self._root / stream_key / f"{batch.checkpoint.digest}.parquet"

    def write(
        self,
        stream_id: str,
        batch: StreamBatch,
        rows: tuple[Mapping[str, object], ...],
    ) -> StreamSinkCommit:
        path = self._path(stream_id, batch)
        if path.exists():
            existing = inspect_parquet(path)
            if existing.rows != len(rows):
                raise RuntimeError(
                    "existing stream batch output has a conflicting row count"
                )
        else:
            if rows:
                write_parquet_rows(path, rows)
            else:
                # A non-empty source batch may legitimately filter to zero rows. Persist
                # an explicit marker so retries remain idempotent without fabricating a
                # Parquet schema for an empty dataset.
                path.parent.mkdir(parents=True, exist_ok=True)
                path.with_suffix(".empty").write_text(
                    batch.checkpoint.digest,
                    encoding="utf-8",
                )
        marker = path if rows else path.with_suffix(".empty")
        if not marker.exists():
            raise RuntimeError("stream sink output was not committed")
        commit_id = f"parquet-batch:{batch.checkpoint.digest}"
        return StreamSinkCommit(
            commit_id,
            len(rows),
            batch.checkpoint.digest,
        )


__all__ = ("ParquetMicroBatchSink",)
