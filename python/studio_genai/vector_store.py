"""Persistent SQLite reference vector store for Ronin RAG execution."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from studio_core.genai import VectorIndexId


@dataclass(frozen=True, slots=True)
class VectorChunk:
    index_id: VectorIndexId
    chunk_id: str
    text: str
    vector: tuple[float, ...]
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.chunk_id or self.chunk_id != self.chunk_id.strip():
            raise ValueError("vector chunk id must be non-empty and trimmed")
        if not self.text or "\x00" in self.text:
            raise ValueError("vector chunk text must be non-empty")
        if not self.vector:
            raise ValueError("vector chunk requires a vector")
        if any(value != value or value in (float("inf"), float("-inf")) for value in self.vector):
            raise ValueError("vector chunk values must be finite")
        metadata = tuple(sorted(self.metadata))
        keys = [key for key, _ in metadata]
        if len(keys) != len(set(keys)):
            raise ValueError("vector chunk metadata keys must be unique")
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class VectorMatch:
    chunk: VectorChunk
    score: float


class SqliteVectorStore:
    """Small persistent cosine-similarity reference store; production backends remain pluggable."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS vector_chunks ("
                "index_id TEXT NOT NULL, chunk_id TEXT NOT NULL, text_value TEXT NOT NULL, "
                "vector_json TEXT NOT NULL, metadata_json TEXT NOT NULL, "
                "PRIMARY KEY(index_id, chunk_id))"
            )
            connection.commit()
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    def replace_index(self, index_id: VectorIndexId, chunks: tuple[VectorChunk, ...]) -> None:
        if any(chunk.index_id != index_id for chunk in chunks):
            raise ValueError("all vector chunks must belong to the replaced index")
        dimensions = {len(chunk.vector) for chunk in chunks}
        if len(dimensions) > 1:
            raise ValueError("all vectors in one index must share a dimension")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM vector_chunks WHERE index_id=?", (str(index_id),))
            for chunk in chunks:
                connection.execute(
                    "INSERT INTO vector_chunks(index_id,chunk_id,text_value,vector_json,metadata_json) "
                    "VALUES (?,?,?,?,?)",
                    (
                        str(index_id),
                        chunk.chunk_id,
                        chunk.text,
                        json.dumps(list(chunk.vector), separators=(",", ":")),
                        json.dumps(dict(chunk.metadata), sort_keys=True, separators=(",", ":")),
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_chunks(self, index_id: VectorIndexId) -> tuple[VectorChunk, ...]:
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT chunk_id,text_value,vector_json,metadata_json FROM vector_chunks "
                "WHERE index_id=? ORDER BY chunk_id",
                (str(index_id),),
            ).fetchall()
            return tuple(
                VectorChunk(
                    index_id,
                    row[0],
                    row[1],
                    tuple(float(value) for value in json.loads(row[2])),
                    tuple(sorted((str(key), str(value)) for key, value in json.loads(row[3]).items())),
                )
                for row in rows
            )
        finally:
            connection.close()

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right):
            raise ValueError("query vector dimension does not match indexed vectors")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)

    def search(
        self,
        index_id: VectorIndexId,
        query_vector: tuple[float, ...],
        *,
        top_k: int,
    ) -> tuple[VectorMatch, ...]:
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100")
        chunks = self.list_chunks(index_id)
        scored = [VectorMatch(chunk, self._cosine(query_vector, chunk.vector)) for chunk in chunks]
        scored.sort(key=lambda item: (-item.score, item.chunk.chunk_id))
        return tuple(scored[:top_k])


__all__ = ("SqliteVectorStore", "VectorChunk", "VectorMatch")
