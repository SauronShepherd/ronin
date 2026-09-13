"""Idempotent Parquet micro-batch sink for the reference streaming runtime."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path

from studio_lakehouse import read_parquet_rows, write_parquet_rows

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
        expected_rows = tuple(dict(row) for row in rows)
        empty_marker = path.with_suffix(".empty")

        if expected_rows:
            if empty_marker.exists():
                raise RuntimeError(
                    "existing stream batch output is an empty marker for a non-empty replay"
                )
            if path.exists():
                existing_rows = read_parquet_rows(path)
                if existing_rows != expected_rows:
                    raise RuntimeError(
                        "existing stream batch output conflicts with replayed row content"
                    )
            else:
                write_parquet_rows(path, expected_rows)
        else:
            if path.exists():
                raise RuntimeError(
                    "existing stream batch output is non-empty for an empty replay"
                )
            if empty_marker.exists():
                if empty_marker.read_text(encoding="utf-8") != batch.checkpoint.digest:
                    raise RuntimeError("existing empty stream batch marker conflicts with checkpoint")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                empty_marker.write_text(batch.checkpoint.digest, encoding="utf-8")

        marker = path if expected_rows else empty_marker
        if not marker.exists():
            raise RuntimeError("stream sink output was not committed")
        return StreamSinkCommit(
            f"parquet-batch:{batch.checkpoint.digest}",
            len(expected_rows),
            batch.checkpoint.digest,
        )


__all__ = ("ParquetMicroBatchSink",)
