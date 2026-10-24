"""Durable SQLite compare-and-set checkpoint store for streaming runtimes."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from hashlib import sha256
from pathlib import Path

from studio_core.canonical_json import encode as encode_canonical_json

from .contracts import StreamCheckpoint, StreamDefinition, StreamPosition


class StreamDefinitionConflict(RuntimeError):
    """Raised when a stream definition cannot safely resume an existing checkpoint."""


class SqliteStreamCheckpointStore:
    """Reference durable checkpoint store with optimistic CAS semantics."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS stream_checkpoints ("
                "stream_id TEXT PRIMARY KEY, checkpoint_json TEXT NOT NULL, "
                "checkpoint_digest TEXT NOT NULL, row_version INTEGER NOT NULL DEFAULT 1)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS stream_definitions ("
                "project_id TEXT NOT NULL, stream_id TEXT NOT NULL, definition_json TEXT NOT NULL, "
                "definition_digest TEXT NOT NULL, PRIMARY KEY(project_id, stream_id))"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS stream_checkpoint_bindings ("
                "runtime_stream_id TEXT PRIMARY KEY, definition_digest TEXT NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=30.0)

    @staticmethod
    def _validate_project_id(project_id: str) -> None:
        if not project_id or project_id != project_id.strip() or "\x00" in project_id:
            raise ValueError("stream project_id must be non-empty and trimmed")

    @staticmethod
    def _validate_stream_id(stream_id: str) -> None:
        if (
            not stream_id
            or stream_id != stream_id.strip()
            or any(character in stream_id for character in ("\n", "\r", "\x00"))
        ):
            raise ValueError("stream_id must be non-empty, trimmed, and single-line")

    @staticmethod
    def runtime_stream_id(project_id: str, stream_id: str) -> str:
        SqliteStreamCheckpointStore._validate_project_id(project_id)
        SqliteStreamCheckpointStore._validate_stream_id(stream_id)
        identity = encode_canonical_json([project_id, stream_id])
        return f"ronin-stream-v1:{sha256(identity).hexdigest()}"

    def get_definition(self, project_id: str, stream_id: str) -> StreamDefinition | None:
        self.runtime_stream_id(project_id, stream_id)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT definition_json FROM stream_definitions WHERE project_id=? AND stream_id=?",
                (project_id, stream_id),
            ).fetchone()
        return None if row is None else StreamDefinition.from_json(str(row[0]))

    def list_definitions(self, project_id: str) -> tuple[StreamDefinition, ...]:
        self._validate_project_id(project_id)
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(
                "SELECT definition_json FROM stream_definitions WHERE project_id=? "
                "ORDER BY stream_id",
                (project_id,),
            ).fetchall()
        return tuple(StreamDefinition.from_json(str(row[0])) for row in rows)

    def commit_stream_bundle_import(
        self,
        project_id: str,
        definitions: tuple[StreamDefinition, ...],
        checkpoint_policies: Mapping[str, str],
    ) -> tuple[tuple[str, str], ...]:
        """Atomically import stream definitions and explicit offset policies."""

        ids = [item.id for item in definitions]
        if len(ids) != len(set(ids)):
            raise ValueError("stream Bundle definitions must have unique ids")
        if set(checkpoint_policies) != set(ids):
            raise ValueError("stream Bundle requires one checkpoint policy per definition")
        if any(policy not in {"reset", "resume"} for policy in checkpoint_policies.values()):
            raise ValueError("stream checkpoint policy must be reset or resume")
        runtime_ids = tuple(
            (item.id, self.runtime_stream_id(project_id, item.id)) for item in definitions
        )
        runtime_id_by_stream = dict(runtime_ids)
        empty_checkpoint = StreamCheckpoint()
        empty_json = self._json(empty_checkpoint)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            for definition in sorted(definitions, key=lambda item: item.id):
                payload = definition.to_json()
                definition_digest = sha256(payload.encode("utf-8")).hexdigest()
                runtime_id = runtime_id_by_stream[definition.id]
                policy = checkpoint_policies[definition.id]
                existing_definition = connection.execute(
                    "SELECT definition_json,definition_digest FROM stream_definitions "
                    "WHERE project_id=? AND stream_id=?",
                    (project_id, definition.id),
                ).fetchone()
                checkpoint = connection.execute(
                    "SELECT checkpoint_json,checkpoint_digest FROM stream_checkpoints "
                    "WHERE stream_id=?",
                    (runtime_id,),
                ).fetchone()
                binding = connection.execute(
                    "SELECT definition_digest FROM stream_checkpoint_bindings "
                    "WHERE runtime_stream_id=?",
                    (runtime_id,),
                ).fetchone()

                if policy == "resume":
                    if (
                        existing_definition is None
                        or existing_definition[0] != payload
                        or existing_definition[1] != definition_digest
                        or checkpoint is None
                        or self._from_json(str(checkpoint[0])).digest != checkpoint[1]
                        or binding is None
                        or binding[0] != definition_digest
                    ):
                        raise StreamDefinitionConflict(
                            "stream definition cannot safely resume its checkpoint: "
                            f"{definition.id}"
                        )
                    continue

                connection.execute(
                    "INSERT INTO stream_definitions(project_id,stream_id,definition_json,"
                    "definition_digest) VALUES (?,?,?,?) ON CONFLICT(project_id,stream_id) "
                    "DO UPDATE SET definition_json=excluded.definition_json, "
                    "definition_digest=excluded.definition_digest",
                    (project_id, definition.id, payload, definition_digest),
                )
                connection.execute(
                    "INSERT INTO stream_checkpoints(stream_id,checkpoint_json,checkpoint_digest) "
                    "VALUES (?,?,?) ON CONFLICT(stream_id) DO UPDATE SET "
                    "checkpoint_json=excluded.checkpoint_json, "
                    "checkpoint_digest=excluded.checkpoint_digest, "
                    "row_version=stream_checkpoints.row_version+1",
                    (runtime_id, empty_json, empty_checkpoint.digest),
                )
                connection.execute(
                    "INSERT INTO stream_checkpoint_bindings(runtime_stream_id,definition_digest) "
                    "VALUES (?,?) ON CONFLICT(runtime_stream_id) DO UPDATE SET "
                    "definition_digest=excluded.definition_digest",
                    (runtime_id, definition_digest),
                )
            connection.commit()
            return runtime_ids
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _json(checkpoint: StreamCheckpoint) -> str:
        return json.dumps(
            {
                "positions": [
                    {"partition": item.partition, "offset": item.offset}
                    for item in checkpoint.positions
                ]
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _from_json(payload: str) -> StreamCheckpoint:
        value = json.loads(payload)
        if not isinstance(value, dict) or set(value) != {"positions"}:
            raise ValueError("stream checkpoint payload has invalid shape")
        positions = value["positions"]
        if not isinstance(positions, list):
            raise ValueError("stream checkpoint positions must be an array")
        parsed: list[StreamPosition] = []
        for item in positions:
            if not isinstance(item, dict) or set(item) != {"partition", "offset"}:
                raise ValueError("stream checkpoint position has invalid shape")
            partition = item["partition"]
            offset = item["offset"]
            if not isinstance(partition, int) or isinstance(partition, bool):
                raise ValueError("stream checkpoint partition must be integer")
            if not isinstance(offset, int) or isinstance(offset, bool):
                raise ValueError("stream checkpoint offset must be integer")
            parsed.append(StreamPosition(partition, offset))
        return StreamCheckpoint(tuple(parsed))

    def get(self, stream_id: str) -> StreamCheckpoint:
        self._validate_stream_id(stream_id)
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT checkpoint_json,checkpoint_digest FROM stream_checkpoints "
                "WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            if row is None:
                return StreamCheckpoint()
            checkpoint = self._from_json(str(row[0]))
            if checkpoint.digest != row[1]:
                raise ValueError("stream checkpoint digest does not match its payload")
            return checkpoint

    def compare_and_set(
        self,
        stream_id: str,
        expected: StreamCheckpoint,
        next_checkpoint: StreamCheckpoint,
    ) -> bool:
        self._validate_stream_id(stream_id)
        with closing(self._connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT checkpoint_digest FROM stream_checkpoints WHERE stream_id=?",
                (stream_id,),
            ).fetchone()
            if row is None:
                if expected.positions:
                    return False
                connection.execute(
                    "INSERT INTO stream_checkpoints(stream_id,checkpoint_json,checkpoint_digest) "
                    "VALUES (?,?,?)",
                    (stream_id, self._json(next_checkpoint), next_checkpoint.digest),
                )
            else:
                if row[0] != expected.digest:
                    connection.rollback()
                    return False
                cursor = connection.execute(
                    "UPDATE stream_checkpoints SET checkpoint_json=?,checkpoint_digest=?,"
                    "row_version=row_version+1 WHERE stream_id=? AND checkpoint_digest=?",
                    (
                        self._json(next_checkpoint),
                        next_checkpoint.digest,
                        stream_id,
                        expected.digest,
                    ),
                )
                if cursor.rowcount != 1:
                    return False
            return True


__all__ = ("SqliteStreamCheckpointStore", "StreamDefinitionConflict")
